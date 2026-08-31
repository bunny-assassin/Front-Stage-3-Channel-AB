#!/usr/bin/env python3
"""Drive ngspice from Python for sweeps that need root-finding.

ngspice's control language can loop, but it cannot easily solve "find the
trimmer position that gives 45 mA, then measure what that setting does at
90 C". That is the question the bias design actually turns on, so it is done
here instead.

    python3 tools/sim_sweep.py q7          choose the bias multiplier device
    python3 tools/sim_sweep.py verify      bias report at the chosen values
    python3 tools/sim_sweep.py comp        sweep the compensation caps
    python3 tools/sim_sweep.py stability   final margins vs load
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "sim"
NGSPICE = ROOT / ".local" / "ngspice" / "bin" / "ngspice"

# The sweep variables are overridden with a second `.param` after the netlist
# include, not with `alterparam`. `alterparam` needs a `reset` to take effect,
# and going through reset leaves the solver in a state from which it reaches the
# spurious collapsed-spreader branch at operating points where a parse-time
# parameter reaches the real one. Concretely: at t_hs = 55 C the reset path lands
# on 1 mA of bias under every option set in the ladder below, while the parse-time
# path finds 41.4 mA under the third. Each probe is its own process anyway, so
# there is nothing that `alterparam` buys here.
DECK = """FS-3W bias probe
.include models.lib
.include channel_core.net
.param rload=4 cload=1p rsrc=2.5k
Vin SRC 0 DC 0
Vshort Q1B_B FB DC 0
.include testbench.inc
.param rv2_b={rv2_b} t_hs={t_hs} t_pcb={t_pcb} r21={r21} r22={r22}
.options {opts}
.control
op
let iq     = 1000*(v(Q12_E)-v(OUT_STAR))/0.22
let spread = v(BIAS_TOP)-v(BIAS_BOT)
let ratio  = spread/(v(BADJ)-v(BIAS_BOT))
let vbe7   = v(BADJ)-v(BIAS_BOT)
let dcerr  = abs(v(OUT_STAR)-v(SPK_OUT))
print iq spread ratio vbe7 dcerr
.endc
.end
"""

# Candidate devices for Q7. The multiplier ratio is not free -- it equals the
# spread the output stage needs divided by Q7's own Vbe -- so the only way to
# move the ratio onto the tracking optimum is to change Q7's die size, which
# changes its Vbe at the same collector current.
Q7_CANDIDATES = [
    ("TTC004B  TO-126N", "QTTC004B"),
    ("MJE15032 TO-220", "QMJE15032"),
    ("NJW0281G TO-3P", "QNJW0281"),
]


AC_DECK = """FS-3W AC probe
.include models.lib
.include channel_core.net
.param rload={rload} cload={cload} rsrc=2.5k
Vin    SRC 0 DC 0 AC 0
Lbreak FB Q1B_B 1e5
Iinj   Q1B_B FB AC 1
.include testbench.inc
.options reltol=1e-4 abstol=1e-11 itl1=1000 rshunt=1e8
.control
set units=radians
op
let iq_check = 1000*(v(Q12_E)-v(OUT_STAR))/0.22
let dc_check = abs(v(OUT_STAR)-v(SPK_OUT))
print iq_check dc_check
alter cc9  = {c9}
alter cc14 = {c14}
ac dec 200 1 100MEG
let Tre = real(-v(FB)/v(Q1B_B))
let Tim = imag(-v(FB)/v(Q1B_B))
let Aom = mag(-v(OUT_STAR)/v(Q1B_B))
wrdata {loop} Tre Tim Aom
alter @iinj[acmag] = 0
alter @vin[acmag] = 1
alter @lbreak[inductance] = 1e-12
ac dec 200 1 10MEG
let Am = mag(v(SPK_OUT))
wrdata {closed} Am
.endc
.end
"""


# Convergence detector. L1 is an ideal inductor, so its DC drop is exactly zero
# in a converged solve and anything nonzero is Newton residual. The useful gate is
# wide: a good solve leaves tens of microvolts, and the failure mode being caught
# here -- the 2 ohm solve landing on 1.9 A of bias instead of 45 mA -- leaves
# 0.11 V. Anything between those is comfortably separated by 1 mV.
DC_RESIDUAL = 1e-3


def _read_cols(path: Path) -> list[list[float]]:
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if parts and all(_isnum(p) for p in parts):
            rows.append([float(p) for p in parts])
    return rows


def _isnum(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _interp(x0, x1, y0, y1, ytarget):
    if y1 == y0:
        return x0
    return x0 + (ytarget - y0) * (x1 - x0) / (y1 - y0)


def margins(freq, mag_db, phase_deg) -> dict[str, float | None]:
    """First 0 dB crossing, phase margin there, and the worst gain margin.

    Phase is unwrapped here rather than relying on ngspice's cph(), whose
    cumulative unwrapping goes wrong over a 1 Hz to 100 MHz sweep. Gain margin
    is taken as the smallest attenuation at ANY frequency where the unwrapped
    phase passes -180, not just the first, because the loop gain can shelf just
    under 0 dB for a decade and cross -180 somewhere in the middle of it.
    """
    ph = list(phase_deg)
    for i in range(1, len(ph)):
        while ph[i] - ph[i - 1] > 180:
            ph[i] -= 360
        while ph[i] - ph[i - 1] < -180:
            ph[i] += 360

    # _interp(x0, x1, y0, y1, ytarget) returns the x where y hits ytarget, so the
    # quantity being solved for goes in the x slots.
    ulgf = pm = None
    for i in range(1, len(freq)):
        if mag_db[i - 1] > 0 >= mag_db[i]:
            ulgf = _interp(freq[i - 1], freq[i], mag_db[i - 1], mag_db[i], 0.0)
            phc = _interp(ph[i - 1], ph[i], mag_db[i - 1], mag_db[i], 0.0)
            pm = 180 + phc
            break

    gm = f_gm = None
    for i in range(1, len(freq)):
        for target in (-180.0, -540.0):
            if (ph[i - 1] - target) * (ph[i] - target) < 0:
                g = _interp(mag_db[i - 1], mag_db[i], ph[i - 1], ph[i], target)
                if gm is None or -g < gm:
                    gm, f_gm = -g, _interp(freq[i - 1], freq[i],
                                           ph[i - 1], ph[i], target)
    return {"ulgf": ulgf, "pm": pm, "gm": gm, "f_gm": f_gm}


def ac_probe(c9: str = "150p", c14: str = "100p", rload: float = 2.0,
             cload: str = "1p") -> dict[str, float | None]:
    """Loop-gain margins for one compensation and load combination."""
    tmp = Path(tempfile.mkdtemp(dir=SIM))
    loop, closed = tmp / "loop.dat", tmp / "closed.dat"
    text = AC_DECK.format(c9=c9, c14=c14, rload=rload, cload=cload,
                          loop=f"{tmp.name}/loop.dat",
                          closed=f"{tmp.name}/closed.dat")
    deck = tmp / "probe.cir"
    deck.write_text(text)
    try:
        out = subprocess.run([str(NGSPICE), "-b", f"{tmp.name}/probe.cir"],
                             cwd=SIM, capture_output=True, text=True,
                             timeout=300).stdout
        checks = {}
        for key in ("iq_check", "dc_check"):
            m = re.search(rf"^{key}\s*=\s*([-\d.e+]+)", out, re.M)
            checks[key] = float(m.group(1)) if m else None
        if checks["dc_check"] is None or checks["dc_check"] > DC_RESIDUAL:
            raise RuntimeError("DC solve did not converge; margins are junk")
        if checks["iq_check"] is None or not 35 < checks["iq_check"] < 60:
            raise RuntimeError(f"bias {checks['iq_check']} mA, not ~45 -- a "
                               f"stability number at the wrong bias means nothing")

        # wrdata writes an x column before every vector: f Tre f Tim f Aom
        rows = _read_cols(loop)
        freq = [r[0] for r in rows]
        tre = [r[1] for r in rows]
        tim = [r[3] for r in rows]
        aom = [r[5] for r in rows]
        import math
        tmag = [math.hypot(a, b) for a, b in zip(tre, tim)]
        tdb = [20 * math.log10(m) if m > 0 else -300 for m in tmag]
        tph = [math.degrees(math.atan2(b, a)) for a, b in zip(tre, tim)]
        res: dict[str, float | None] = dict(margins(freq, tdb, tph))

        aodb = [20 * math.log10(m) if m > 0 else -300 for m in aom]
        res["f_aol0"] = None
        for i in range(1, len(freq)):
            if aodb[i - 1] > 0 >= aodb[i]:
                res["f_aol0"] = _interp(freq[i - 1], freq[i],
                                        aodb[i - 1], aodb[i], 0.0)
                break

        def at(f):
            for i in range(1, len(freq)):
                if freq[i - 1] <= f <= freq[i]:
                    w = (f - freq[i - 1]) / (freq[i] - freq[i - 1])
                    return tdb[i - 1] + w * (tdb[i] - tdb[i - 1])
            return None
        res["t1k"], res["t20k"] = at(1e3), at(20e3)

        crows = _read_cols(closed)
        cf = [r[0] for r in crows]
        cm = [20 * math.log10(r[1]) if r[1] > 0 else -300 for r in crows]
        res["av1k"] = next((cm[i] for i in range(len(cf)) if cf[i] >= 1e3), None)
        res["pk"] = max(cm)
        # Closed-loop -3 dB, referred to the 1 kHz gain. This is the honest
        # bandwidth figure: it includes the input pole at C7, which the loop
        # gain does not see because C7 sits outside the feedback loop.
        res["f3db"] = None
        if res["av1k"] is not None:
            ref = res["av1k"] - 3.0
            for i in range(1, len(cf)):
                if cf[i] > 1e3 and cm[i - 1] > ref >= cm[i]:
                    res["f3db"] = _interp(cf[i - 1], cf[i],
                                          cm[i - 1], cm[i], ref)
                    break
        return res
    finally:
        for p in (loop, closed, deck):
            p.unlink(missing_ok=True)
        tmp.rmdir()


# The loop is closed with a 0 V source, not a small resistor. Both are the same
# circuit, but at 2 ohm the resistor version will not solve: it lands on a 1.9 A
# bias point while the 0 V source lands on 44.5 mA. A 0 V source gets its own
# branch current unknown in the matrix, whereas a near-zero resistor puts a
# near-singular row in it. Every load and every analysis below therefore closes
# the loop the same way, so the operating point cannot silently differ between
# the AC margins and the distortion numbers.
THD_DECK = """FS-3W THD probe
.include models.lib
.include channel_core.net
.param rload={rload} cload={cload} rsrc=2.5k
Vsig   SRC 0 SIN(0 {amp} {freq})
Vshort Q1B_B FB DC 0
.include testbench.inc
.options reltol=1e-4 abstol=1e-11 itl1=1000 rshunt=1e8
.control
op
let iq_check = 1000*(v(Q12_E)-v(OUT_STAR))/0.22
let dc_check = abs(v(OUT_STAR)-v(SPK_OUT))
print iq_check dc_check
tran {tstep} {tstop} {tstart}
linearize v(spk_out)
fourier {freq} v(spk_out)
.endc
.end
"""

SLEW_DECK = """FS-3W slew probe
.include models.lib
.include channel_core.net
.param rload={rload} cload={cload} rsrc=2.5k
Vsq    SRC 0 PULSE(0 {amp} 5u 20n 20n 30u 60u)
Vshort Q1B_B FB DC 0
.include testbench.inc
.options reltol=1e-4 abstol=1e-11 itl1=1000 rshunt=1e8
.control
op
let iq_check = 1000*(v(Q12_E)-v(OUT_STAR))/0.22
let dc_check = abs(v(OUT_STAR)-v(SPK_OUT))
print iq_check dc_check
tran 5n 34u
wrdata {wave} v(spk_out)
.endc
.end
"""

# Edge at 5 us, flat top until 35 us, and the run stops at 34 us so that no
# window can reach the falling edge. Both of those matter. The top has to be long
# compared with the settling or the ringing window lands on the tail of the rise
# and calls a rise ringing; and the run has to stop before the fall or the
# "settled" average is taken across the fall and everything after it is nonsense.
EDGE_T = 5e-6
SETTLE_FROM = 28e-6   # flat by here, and still 6 us clear of the falling edge
RING_FROM = 20e-6     # anything still moving here is real ringing


def _checked(out: str) -> None:
    vals = {}
    for key in ("iq_check", "dc_check"):
        m = re.search(rf"^{key}\s*=\s*([-\d.e+]+)", out, re.M)
        vals[key] = float(m.group(1)) if m else None
    if vals["dc_check"] is None or vals["dc_check"] > DC_RESIDUAL:
        raise RuntimeError(f"DC solve did not converge "
                           f"(L1 drop {vals['dc_check']})")
    if vals["iq_check"] is None or not 35 < vals["iq_check"] < 60:
        raise RuntimeError(f"bias {vals['iq_check']} mA, not ~45")


def thd_probe(freq: float, amp: float, rload: float,
              cload: str = "1p") -> dict[str, float]:
    """THD from a fourier analysis of one sine, at one load."""
    cycles = 10
    tstart = 5e-3 if freq < 5e3 else 500e-6
    tstop = tstart + cycles / freq
    tstep = min(1 / (freq * 500), 200e-9)
    text = THD_DECK.format(rload=rload, cload=cload, amp=amp, freq=freq,
                           tstep=tstep, tstop=tstop, tstart=tstart)
    tmp = Path(tempfile.mkdtemp(dir=SIM))
    deck = tmp / "thd.cir"
    deck.write_text(text)
    try:
        out = subprocess.run([str(NGSPICE), "-b", f"{tmp.name}/thd.cir"],
                             cwd=SIM, capture_output=True, text=True,
                             timeout=900).stdout
        _checked(out)
        m = re.search(r"THD:\s*([\d.e+-]+)\s*%", out)
        if not m:
            raise RuntimeError("no THD in fourier output")
        res = {"thd": float(m.group(1))}
        h = re.findall(r"^\s*(\d+)\s+[\d.e+-]+\s+([\d.e+-]+)\s+[-\d.e+]+\s+"
                       r"([\d.e+-]+)", out, re.M)
        by_n = {int(n): (float(mag), float(nm)) for n, mag, nm in h}
        res["fund"] = by_n.get(1, (0, 0))[0]
        for n in (2, 3, 5, 7):
            res[f"h{n}"] = 100 * by_n.get(n, (0, 0))[1]
        return res
    finally:
        deck.unlink(missing_ok=True)
        tmp.rmdir()


def slew_probe(rload: float, cload: str = "1p",
               amp: float = 1.126) -> dict[str, float]:
    """Slew rate and square-wave settling, measured off the waveform.

    The pulse steps from 0 to `amp` rather than from -amp to +amp so that the
    operating point the transient starts from is the idle one, which lets the
    bias precondition below mean something. Sign of `amp` picks which half of
    the output swing gets exercised; both are run, because a difference between
    them is the VAS running out of current in one direction.

    Measured off the waveform rather than with ngspice `meas` so the numbers can
    be checked against the shape instead of trusting a single crossing.
    """
    tmp = Path(tempfile.mkdtemp(dir=SIM))
    wave, deck = tmp / "slew.dat", tmp / "slew.cir"
    deck.write_text(SLEW_DECK.format(rload=rload, cload=cload, amp=amp,
                                     wave=f"{tmp.name}/slew.dat"))
    try:
        out = subprocess.run([str(NGSPICE), "-b", f"{tmp.name}/slew.cir"],
                             cwd=SIM, capture_output=True, text=True,
                             timeout=900).stdout
        _checked(out)
        rows = _read_cols(wave)
        t = [r[0] for r in rows]
        v = [r[1] for r in rows]

        seg = [(tt, vv) for tt, vv in zip(t, v) if EDGE_T <= tt]
        settled = [vv for tt, vv in seg if tt >= SETTLE_FROM]
        final = sum(settled) / len(settled)
        start = seg[0][1]
        span = final - start
        a, b = start + 0.1 * span, start + 0.9 * span

        # First contiguous 10-90 crossing. Collecting every sample inside the
        # band and taking max minus min instead would fold any later excursion
        # back into the band into the risetime and report an absurdly slow edge.
        def first_at(level):
            for tt, vv in seg:
                if (vv >= level) if span > 0 else (vv <= level):
                    return tt
            return None

        ta, tb = first_at(a), first_at(b)
        res = {"final": final}
        res["t_rise"] = (tb - ta) * 1e6 if ta and tb else None
        res["sr"] = abs(0.8 * span) / (tb - ta) / 1e6 if ta and tb else None
        # Bandwidth a single-pole response with this risetime would have. The
        # step is a clean exponential, so this is the honest way to state the
        # speed of the thing.
        res["bw_khz"] = 0.35 / res["t_rise"] * 1e3 if res["t_rise"] else None

        # Overshoot, sign-corrected so >0 always means "went past the target".
        s = 1.0 if final > 0 else -1.0
        res["overshoot"] = 100 * (max(s * vv for _, vv in seg) - abs(final)) \
            / abs(final)
        # Anything still moving 15 us after the edge is ringing, not risetime.
        tail = [vv for tt, vv in seg if RING_FROM <= tt]
        res["ring"] = 100 * max(abs(x - final) for x in tail) / abs(final)
        return res
    finally:
        for p in (wave, deck):
            p.unlink(missing_ok=True)
        tmp.rmdir()


def headroom(rload: float, thd_gate: float, freq: float = 1e3,
             lo: float = 0.5, hi: float = 1.4) -> tuple[float, float]:
    """Largest output that stays under `thd_gate` percent, and its power.

    Bisects on drive level. Clipping here is a hard ceiling rather than a soft
    knee -- the output stops at V_rail minus the ballast drop minus the output
    device's saturation voltage -- so THD goes from 0.002 % to 16 % over about
    2 % of drive, and a bisection is the only honest way to find the edge.
    """
    best = (0.0, 0.0)
    for _ in range(9):
        mid = 0.5 * (lo + hi)
        try:
            v = thd_probe(freq, mid, rload)
        except RuntimeError:
            hi = mid
            continue
        if v["thd"] <= thd_gate:
            best = (v["fund"], v["fund"] ** 2 / (2 * rload))
            lo = mid
        else:
            hi = mid
    return best


def netlist_for(q7_model: str | None) -> None:
    cmd = [sys.executable, str(ROOT / "tools" / "gen_spice.py"),
           "-o", str(SIM / "channel_core.net")]
    if q7_model:
        cmd += ["--model", f"Q7={q7_model}"]
    subprocess.run(cmd, cwd=ROOT, capture_output=True, check=True)


# Newton stalls on this circuit at scattered parameter values. These are tried
# in order until one produces a solution that passes the L1 check. rshunt is the
# effective one: it puts a 10 G resistor from every node to ground, which keeps
# the high-impedance VAS and bias nodes from going singular during iteration.
OPTION_SETS = [
    "gminsteps=250 itl1=1000 gmin=1e-11 rshunt=1e9",
    "gminsteps=100 itl1=1000 rshunt=1e10",
    "gminsteps=250 itl1=1000 reltol=1e-4 rshunt=1e9 abstol=1e-11",
    "gminsteps=100 itl1=500",
]


def _probe_once(rv2_b, r21, r22, t_hs, t_pcb, opts) -> dict[str, float]:
    text = DECK.format(rv2_b=rv2_b, r21=r21, r22=r22, t_hs=t_hs, t_pcb=t_pcb,
                       opts=opts)
    with tempfile.NamedTemporaryFile("w", dir=SIM, suffix=".cir",
                                     delete=False) as fh:
        fh.write(text)
        path = Path(fh.name)
    try:
        out = subprocess.run([str(NGSPICE), "-b", path.name], cwd=SIM,
                             capture_output=True, text=True, timeout=120).stdout
    finally:
        path.unlink(missing_ok=True)
    vals = {}
    for key in ("iq", "spread", "ratio", "vbe7", "dcerr"):
        m = re.search(rf"^{key}\s*=\s*([-\d.e+]+)", out, re.M)
        if not m:
            raise RuntimeError(f"ngspice did not report {key}:\n{out[-2000:]}")
        vals[key] = float(m.group(1))
    # A DC solve that silently fell back to a transient operating point is worse
    # than no answer, because it looks like an answer. L1 is a DC short, so any
    # voltage across it means the reported state is not a DC solution.
    if vals["dcerr"] > DC_RESIDUAL:
        raise RuntimeError(f"DC solve did not converge (L1 drop "
                           f"{vals['dcerr']:.2e} V across a short)")
    # A residual check cannot catch everything. This circuit has a second,
    # spurious DC solution in which the bias spreader collapses: Q7 saturates,
    # the spread drops to a few tens of millivolts and the output stage sits at
    # about 1 mA. It satisfies the equations, so the L1 residual is clean and it
    # reports as success -- it turned up as a lone 1.1 mA row in the middle of a
    # temperature sweep whose neighbours were both 42 mA. The spreader has to
    # drop roughly six Vbe by construction, so anything under 2 V is that
    # solution and not a bias point this circuit can actually sit at.
    if vals["spread"] < 2.0:
        raise RuntimeError(f"spurious solution: bias spreader collapsed to "
                           f"{vals['spread']:.3f} V (needs ~3.9 V)")
    return vals


def probe(rv2_b: float, r21: float = 4420.0, r22: float = 816.0,
          t_hs: float = 25.0, t_pcb: float = 25.0) -> dict[str, float]:
    """Solve one operating point, retrying past isolated convergence failures.

    The collapsed-spreader branch is a Newton artefact at scattered (trimmer,
    temperature) points, not a second physical operating point: a 0.5 C nudge
    in heatsink temperature, or a milliohm of trimmer, is enough to leave it
    and the neighbours on either side are the real 40 mA solution. The retry
    ladder therefore varies the thing that is physically continuous, not just
    the solver options.
    """
    last = None
    for opts in OPTION_SETS:
        for dt in (0.0, 0.5, -0.5, 1.0):
            for nudge in (0.0, 1e-3, -1e-3):
                try:
                    return _probe_once(rv2_b + nudge, r21, r22,
                                       t_hs + dt, t_pcb, opts)
                except RuntimeError as e:
                    last = e
    raise last


def solve_r22(target_ma: float, r21: float = 4420.0,
              lo=200.0, hi=4000.0) -> float | None:
    """Bisect the lower leg for a target idle current, trimmer at mid-travel.

    Raising R22 raises the divider tap, which lowers the ratio, the spread and
    the bias, so Iq is monotonically decreasing in R22.
    """
    if probe(50.0, r21, lo)["iq"] < target_ma:
        return None
    if probe(50.0, r21, hi)["iq"] > target_ma:
        return None
    for _ in range(28):
        mid = 0.5 * (lo + hi)
        if probe(50.0, r21, mid)["iq"] > target_ma:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def cmd_q7() -> int:
    target = 45.0
    print("Choosing Q7. For each candidate: solve R22 so the trimmer sits at")
    print("mid-travel with 45 mA per device at 25 C, then heat the heatsink to")
    print("90 C. Flat is the goal. A rising bias is a runaway risk; a falling")
    print("one means the stage slides into class B exactly when it is working.")
    print("\nThe ratio column is the point: it is forced to spread/Vbe7, so a")
    print("bigger Q7 die means a lower Vbe7 and a higher achievable ratio.\n")
    print(f"{'Q7':<18} {'Vbe7':>6} {'ratio':>6} {'spread':>7} {'R22':>6} "
          f"{'Iq@25':>7} {'Iq@90':>7} {'drift':>7}")
    print(f"{'':<18} {'(V)':>6} {'':>6} {'(V)':>7} {'(ohm)':>6} "
          f"{'(mA)':>7} {'(mA)':>7} {'':>7}")
    results = []
    for label, model in Q7_CANDIDATES:
        netlist_for(model)
        try:
            r22 = solve_r22(target)
        except RuntimeError as e:
            print(f"{label:<18} solve failed: {e}")
            continue
        if r22 is None:
            print(f"{label:<18} no R22 in 200-4000 ohm reaches 45 mA")
            continue
        c = probe(50.0, 4420.0, r22)
        hot = probe(50.0, 4420.0, r22, t_hs=90.0)
        drift = hot["iq"] / c["iq"]
        print(f"{label:<18} {c['vbe7']:>6.3f} {c['ratio']:>6.3f} "
              f"{c['spread']:>7.3f} {r22:>6.0f} {c['iq']:>7.1f} "
              f"{hot['iq']:>7.1f} {drift:>6.2f}x")
        results.append((label, model, r22, drift))
    netlist_for(None)
    if results:
        best = min(results, key=lambda r: abs(r[3] - 1.0))
        print(f"\nflattest: {best[0]} with R22 = {best[2]:.0f} ohm, "
              f"drift {best[3]:.2f}x over 65 C")
    return 0


def cmd_verify() -> int:
    """Report the as-drawn design: values come from channel_netlist, not args."""
    from channel_netlist import COMPONENTS
    from gen_spice import parse_value
    by_ref = {c.ref: c for c in COMPONENTS}
    r21 = parse_value(by_ref["R21"].value)
    r22 = parse_value(by_ref["R22"].value)
    netlist_for(None)
    print(f"as drawn: R21 = {r21:.0f}, R22 = {r22:.0f}, RV2 = 100 ohm\n")

    def trim(target):
        lo, hi = 0.0, 100.0
        if probe(lo, r21, r22)["iq"] < target or \
           probe(hi, r21, r22)["iq"] > target:
            return None
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            if probe(mid, r21, r22)["iq"] > target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    pos = trim(45.0)
    if pos is None:
        v0, v1 = probe(0.0, r21, r22)["iq"], probe(100.0, r21, r22)["iq"]
        print(f"FAIL: trimmer range is {v1:.1f}-{v0:.1f} mA, "
              f"which does not include 45 mA")
        return 1
    print(f"trimmer setpoint {pos:.1f} ohm of 100 ({pos:.0f}% travel)\n")
    print(f"{'T_hs':>5} {'T_pcb':>6} {'spread':>8} {'ratio':>7} "
          f"{'Iq/dev':>8} {'Pd/dev':>8} {'4-dev':>7}")
    print(f"{'(C)':>5} {'(C)':>6} {'(V)':>8} {'':>7} {'(mA)':>8} "
          f"{'(W)':>8} {'(W)':>7}")
    for t_hs, t_pcb in ((25, 25), (40, 30), (55, 35), (70, 40), (90, 45)):
        v = probe(pos, r21, r22, t_hs=t_hs, t_pcb=t_pcb)
        pd = 0.024 * v["iq"]
        print(f"{t_hs:>5} {t_pcb:>6} {v['spread']:>8.3f} {v['ratio']:>7.3f} "
              f"{v['iq']:>8.1f} {pd:>8.2f} {4*pd:>7.1f}")
    print("\ntrim range at 25 C:")
    for p_i in (0.0, pos, 100.0):
        v = probe(p_i, r21, r22)
        tag = {0.0: "min travel", 100.0: "max travel / wiper open"}.get(
            p_i, "setpoint")
        print(f"  RV2_lo={p_i:>5.1f}  spread={v['spread']:.3f} V  "
              f"Iq={v['iq']:>7.1f} mA  Pd={0.024*v['iq']:>5.1f} W/dev  {tag}")
    return 0


def _row(tag, v):
    def f(k, w, p=1):
        x = v.get(k)
        return f"{x:>{w}.{p}f}" if x is not None else f"{'--':>{w}}"
    return (f"{tag:<16} {f('f_aol0',9,0)} {f('ulgf',9,0)} {f('pm',6)} "
            f"{f('gm',6)} {f('t1k',6)} {f('t20k',6)} {f('av1k',6,2)} "
            f"{f('pk',6,2)} {f('f3db',8,0)}")


def _hdr():
    print(f"{'':<16} {'f_Aol=0':>9} {'ULGF':>9} {'PM':>6} {'GM':>6} "
          f"{'T@1k':>6} {'T@20k':>6} {'Acl':>6} {'peak':>6} {'Acl -3dB':>8}")
    print(f"{'':<16} {'(Hz)':>9} {'(Hz)':>9} {'(deg)':>6} {'(dB)':>6} "
          f"{'(dB)':>6} {'(dB)':>6} {'(dB)':>6} {'(dB)':>6} {'(Hz)':>8}")


def cmd_comp() -> int:
    print("Compensation sweep at 2 ohm. Gates: PM >= 60 deg, GM >= 10 dB, and")
    print("T@20k as high as those allow -- loop gain at the top of the band is")
    print("what linearises the output stage where it is least linear.\n")
    print("C14 sits across the feedback resistor. Raising the feedback factor at")
    print("HF flattens the loop gain into a shelf that hangs just under 0 dB for")
    print("a decade, and the phase keeps rotating through it, so C14 buys closed-")
    print("loop bandwidth limiting at the direct cost of gain margin.\n")
    netlist_for(None)
    for c14 in ("100p", "47p", "22p", "10p", "1f"):
        print(f"--- C14 = {c14} " + "-" * 52)
        _hdr()
        for c9 in ("150p", "100p", "68p", "47p", "33p"):
            try:
                v = ac_probe(c9=c9, c14=c14)
            except RuntimeError as e:
                print(f"{'C9=' + c9:<16} failed: {e}")
                continue
            print(_row(f"C9={c9}", v))
        print()
    return 0


def cmd_stability() -> int:
    """Final margins for the as-drawn compensation against every load it sees."""
    from channel_netlist import COMPONENTS
    by_ref = {c.ref: c for c in COMPONENTS}
    c9, c14 = by_ref["C9"].value, by_ref["C14"].value
    netlist_for(None)
    print(f"as drawn: C9 (Cdom) = {c9}, C14 = {c14}\n")
    print("Loads: 4 ohm is the tweeter and midrange, 2 ohm the midbass. The")
    print("capacitive cases stand in for cable and for an electrostatic or")
    print("ribbon tweeter, which is the worst load this will ever drive.\n")
    _hdr()
    cases = [("4 ohm", 4.0, "1p"), ("2 ohm", 2.0, "1p"),
             ("4 ohm + 100n", 4.0, "100n"), ("2 ohm + 100n", 2.0, "100n"),
             ("2 ohm + 470n", 2.0, "470n"), ("2 ohm + 2u2", 2.0, "2.2u"),
             ("8 ohm + 2u2", 8.0, "2.2u")]
    worst_pm, worst_gm = 1e9, 1e9
    for tag, rl, cl in cases:
        try:
            v = ac_probe(c9=c9, c14=c14, rload=rl, cload=cl)
        except RuntimeError as e:
            print(f"{tag:<16} failed: {e}")
            continue
        print(_row(tag, v))
        if v["pm"] is not None:
            worst_pm = min(worst_pm, v["pm"])
        if v["gm"] is not None:
            worst_gm = min(worst_gm, v["gm"])
    print(f"\nworst case: phase margin {worst_pm:.1f} deg (gate 60), "
          f"gain margin {worst_gm:.1f} dB (gate 10)")
    return 0 if worst_pm >= 60 and worst_gm >= 10 else 1


def cmd_thd() -> int:
    """Distortion and large-signal behaviour at every rated operating point.

    Each case is its own ngspice process. Sharing one process and using `alter`
    to change the load looks tidier but does not work: after `alter rload = 2`
    the next DC solve lands on a 1.9 A bias point instead of 45 mA, and every
    number taken after that is fiction.
    """
    netlist_for(None)
    # 1.033 V peak in gives 20.5 V peak out, which is 52 W into 4 ohm and 105 W
    # into 2 ohm. The input level includes the 2.5k/100k divider ahead of the
    # LTP. 2 ohm is NOT driven to the 21.8 V peak that an earlier revision of
    # docs/01 called 119 W: the output stage ceiling is 21.45 V, so that number
    # was on the wrong side of hard clipping. See the headroom table below.
    print("Distortion, full rated output. Simulated THD is a floor, not a")
    print("prediction: it has no layout coupling and no supply ripple.\n")
    print(f"{'case':<22}{'THD %':>9}{'H2 %':>9}{'H3 %':>9}{'H5 %':>9}"
          f"{'Vpk':>8}")
    print("-" * 65)
    ok = True
    for tag, f, amp, rl in [("1 kHz, 4 ohm, 52 W", 1e3, 1.033, 4.0),
                            ("1 kHz, 2 ohm, 105 W", 1e3, 1.033, 2.0),
                            ("20 kHz, 4 ohm, 52 W", 20e3, 1.033, 4.0),
                            ("20 kHz, 2 ohm, 105 W", 20e3, 1.033, 2.0),
                            ("1 kHz, 4 ohm, 1 W", 1e3, 0.146, 4.0),
                            ("20 kHz, 4 ohm, 1 W", 20e3, 0.146, 4.0)]:
        try:
            v = thd_probe(f, amp, rl)
        except RuntimeError as e:
            print(f"{tag:<22} failed: {e}")
            ok = False
            continue
        print(f"{tag:<22}{v['thd']:>9.4f}{v['h2']:>9.4f}{v['h3']:>9.4f}"
              f"{v['h5']:>9.4f}{v['fund']:>8.1f}")

    print("\nClipping ceiling. The rails are regulated, so unlike an")
    print("unregulated amplifier these numbers do not move with battery")
    print("voltage: what clips at 14.4 V input also clips at 11 V.\n")
    print(f"{'load':<10}{'0.01% THD':>22}{'0.1% THD':>22}{'1% THD':>22}")
    print("-" * 76)
    for tag, rl in [("4 ohm", 4.0), ("2 ohm", 2.0)]:
        cells = []
        for gate in (0.01, 0.1, 1.0):
            vpk, pw = headroom(rl, gate)
            cells.append(f"{vpk:.1f} Vpk / {pw:.0f} W")
        print(f"{tag:<10}" + "".join(f"{c:>22}" for c in cells))

    print("\nFull-output step response, driven from the worst-case 2.5 k source")
    print("impedance at the gain trimmer wiper. Overshoot and ringing are the")
    print("time-domain view of the phase margin from `stability`.\n")
    print(f"{'case':<22}{'Vfinal':>9}{'trise us':>10}{'~BW kHz':>10}"
          f"{'V/us':>8}{'over %':>9}{'ring %':>9}")
    print("-" * 77)
    worst_sr = 1e9
    for tag, rl, cl, amp in [("4 ohm, +swing", 4.0, "1p", 1.033),
                             ("4 ohm, -swing", 4.0, "1p", -1.033),
                             ("2 ohm, +swing", 2.0, "1p", 1.033),
                             ("2 ohm, -swing", 2.0, "1p", -1.033),
                             ("2 ohm + 100n", 2.0, "100n", 1.033),
                             ("2 ohm + 470n", 2.0, "470n", 1.033),
                             ("2 ohm + 2u2", 2.0, "2.2u", 1.033)]:
        try:
            v = slew_probe(rl, cl, amp)
        except RuntimeError as e:
            print(f"{tag:<22} failed: {e}")
            ok = False
            continue
        print(f"{tag:<22}{v['final']:>9.2f}{v['t_rise']:>10.2f}"
              f"{v['bw_khz']:>10.0f}{v['sr']:>8.1f}{v['overshoot']:>9.2f}"
              f"{v['ring']:>9.2f}")
        worst_sr = min(worst_sr, v["sr"])

    # Slew limiting means the edge takes the same time however small the step,
    # so the slope stops scaling with amplitude. Driving the same edge 10x
    # smaller and comparing slope-per-volt settles it: a ratio near 1 means the
    # response is linear and there is no slew limit anywhere below full output.
    print("\nIs any of that slew limiting? Compare slope per volt of step at")
    print("full output against one tenth of it. Equal means linear.\n")
    full = slew_probe(4.0, "1p", 1.033)
    tenth = slew_probe(4.0, "1p", 0.1033)
    n_full = full["sr"] / abs(full["final"])
    n_tenth = tenth["sr"] / abs(tenth["final"])
    print(f"  full output  {full['final']:6.2f} V step, "
          f"{full['sr']:5.1f} V/us -> {n_full:.4f} per V")
    print(f"  one tenth    {tenth['final']:6.2f} V step, "
          f"{tenth['sr']:5.1f} V/us -> {n_tenth:.4f} per V")
    ratio = n_full / n_tenth
    linear = 0.9 <= ratio <= 1.1
    print(f"  ratio {ratio:.3f} -- "
          f"{'linear, no slew limiting' if linear else 'SLEW LIMITED'}")
    print(f"\nworst edge {worst_sr:.1f} V/us, against the 2.74 V/us a full-scale"
          f" 20 kHz sine needs")
    return 0 if ok and linear and worst_sr > 2.74 * 3 else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mode",
                   choices=("q7", "verify", "comp", "stability", "thd"))
    a = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return {"q7": cmd_q7, "verify": cmd_verify, "comp": cmd_comp,
            "stability": cmd_stability, "thd": cmd_thd}[a.mode]()


if __name__ == "__main__":
    sys.exit(main())
