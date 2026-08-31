#!/usr/bin/env python3
"""Design calculations for the FS-3W front-stage amplifier.

Every number quoted in docs/ is produced here so the design can be re-derived
and audited after a spec change. Run with no arguments to print all sections.

    python3 tools/design_calcs.py
"""

from __future__ import annotations

import math

# ----------------------------------------------------------------------------
# Design inputs
# ----------------------------------------------------------------------------

RAIL = 24.0            # regulated main rail, volts
RAIL_FE = 30.0         # front-end (LTP/VAS/pre-driver) rail, volts
# Output stage saturation, i.e. what is lost between the rail and the emitters
# once the device is fully driven, NOT counting the ballast drop. The ballast is
# accounted for separately because its drop depends on load current, which is
# what makes the clipping level load-dependent. 1.4 V matches the simulated
# 21.4 V ceiling at the 2 ohm peak of 10.7 A.
VCE_SAT = 1.4
LOADS = {"tweeter": 4.0, "mid": 4.0, "midbass": 2.0}
PAIRS_PER_CH = 2       # complementary output pairs per channel
RE = 0.22              # output emitter (ballast) resistor, ohms
I_QUIESCENT = 0.045    # bias current per output device, amps
GAIN = 20.0            # power amp stage closed-loop voltage gain (V/V)

T_AMBIENT = 40.0       # worst-case in-cabin ambient, degC
TJ_MAX_DERATED = 125.0 # design limit for output device junction temp, degC
RTH_JC = 0.7           # NJW0281G junction-to-case, degC/W
RTH_CS = 0.25          # case-to-sink with thermal pad + clamp, degC/W

# ----------------------------------------------------------------------------


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def power_and_current() -> dict:
    """Clipping power, peak current and worst-case dissipation per channel."""
    section("1. OUTPUT POWER, CURRENT AND DISSIPATION")
    # The clipping level is load-dependent and solving for it takes one line of
    # algebra rather than a fixed headroom figure. The emitters can reach
    # RAIL - VCE_SAT, and the ballast then drops I_peak * (RE / PAIRS_PER_CH)
    # on the way to the speaker terminal, with I_peak = vpk / rl:
    #     vpk = RAIL - VCE_SAT - vpk * Rb / rl
    #     vpk = (RAIL - VCE_SAT) / (1 + Rb / rl)
    # Using one load-independent loss instead overstates the 2 ohm channel,
    # which is exactly how this design came to be documented as 119 W into
    # 2 ohm when it actually clips at 113 W.
    rb = RE / PAIRS_PER_CH
    print(f"Rail: +/-{RAIL:.1f} V   Vce(sat): {VCE_SAT:.1f} V   "
          f"ballast per polarity: {rb:.3f} ohm ({PAIRS_PER_CH} x {RE} ohm)")
    print()
    hdr = (f"{'channel':<10}{'load':>7}{'V_peak':>9}{'P_clip':>10}"
           f"{'I_peak':>9}{'I_pk/dev':>10}{'P_diss_max':>12}")
    print(hdr)
    print("-" * len(hdr))
    results = {}
    total_diss = 0.0
    total_out = 0.0
    vpk = 0.0
    for name, rl in LOADS.items():
        vpk = (RAIL - VCE_SAT) / (1 + rb / rl)
        p_clip = vpk ** 2 / (2 * rl)
        i_peak = vpk / rl
        i_dev = i_peak / PAIRS_PER_CH
        # Classic class-B worst case: max at Vout_peak = 2*Vcc/pi
        p_diss = RAIL ** 2 / (math.pi ** 2 * rl)
        results[name] = dict(rl=rl, vpk=vpk, p_clip=p_clip, i_peak=i_peak,
                             i_dev=i_dev, p_diss=p_diss)
        total_diss += p_diss
        total_out += p_clip
        print(f"{name:<10}{rl:>6.0f}R{vpk:>8.1f}V{p_clip:>9.1f}W{i_peak:>8.2f}A"
              f"{i_dev:>9.2f}A{p_diss:>11.1f}W")
    print("-" * len(hdr))
    p_q = 2 * PAIRS_PER_CH * len(LOADS) * I_QUIESCENT * RAIL
    print(f"Sum of clipping power (all 3 ch)          : {total_out:.0f} W")
    print(f"Worst-case class-B dissipation (all 3 ch) : {total_diss:.1f} W")
    print(f"Quiescent dissipation, output stage       : {p_q:.1f} W "
          f"({2 * PAIRS_PER_CH * len(LOADS)} devices @ {I_QUIESCENT*1000:.0f} mA)")
    print(f"Design thermal load for heatsink          : {total_diss + p_q:.1f} W")
    results["_totals"] = dict(p_out=total_out, p_diss=total_diss, p_q=p_q,
                              p_thermal=total_diss + p_q, vpk=vpk)
    return results


def heatsink(res: dict) -> None:
    section("2. HEATSINK AND DEVICE THERMAL BUDGET")
    p_thermal = res["_totals"]["p_thermal"]
    # Worst single device: midbass channel, dissipation split over 4 devices
    p_dev = res["midbass"]["p_diss"] / (2 * PAIRS_PER_CH)
    print(f"Worst-case dissipation in one midbass output device: {p_dev:.1f} W")
    budget = TJ_MAX_DERATED - T_AMBIENT
    print(f"Available rise, junction to ambient: {budget:.0f} degC "
          f"(Tj {TJ_MAX_DERATED:.0f} - Tamb {T_AMBIENT:.0f})")
    rise_jc = p_dev * RTH_JC
    rise_cs = p_dev * RTH_CS
    print(f"  junction->case  : {rise_jc:5.1f} degC  (Rth {RTH_JC} degC/W)")
    print(f"  case->sink      : {rise_cs:5.1f} degC  (Rth {RTH_CS} degC/W)")
    remaining = budget - rise_jc - rise_cs
    print(f"  left for sink->ambient: {remaining:.1f} degC")
    rth_sa = remaining / p_thermal
    print(f"\nRequired sink-to-ambient thermal resistance for the whole board:")
    print(f"  {remaining:.1f} degC / {p_thermal:.1f} W = {rth_sa:.3f} degC/W")
    print(f"  -> specify chassis heatsink <= {rth_sa:.2f} degC/W natural convection")
    for label, rth in (("finned chassis, 250x175mm, 30mm fins", 0.45),
                       ("same with 40 CFM forced air", 0.20)):
        print(f"  {label:<40} {rth:>5.2f} degC/W -> "
              f"sink rise {p_thermal * rth:5.1f} degC, "
              f"Tj {T_AMBIENT + p_thermal*rth + rise_cs + rise_jc:5.1f} degC")


def front_end() -> None:
    section("3. FRONT-END: GAIN, COMPENSATION, SLEW RATE, NOISE")
    i_tail = 4.0e-3          # LTP tail current
    re_deg = 220.0           # LTP emitter degeneration per side
    cdom = 68e-12            # dominant-pole (Miller) cap, C9 as drawn
    ic = i_tail / 2
    re_intrinsic = 0.026 / ic
    gm = 1.0 / (2 * (re_intrinsic + re_deg))
    print(f"LTP tail current      : {i_tail*1e3:.1f} mA  ({ic*1e3:.1f} mA per side)")
    print(f"Intrinsic re          : {re_intrinsic:.1f} ohm")
    print(f"Emitter degeneration  : {re_deg:.0f} ohm per side")
    print(f"Input stage gm        : {gm*1e3:.3f} mS")
    print(f"Cdom (C9)             : {cdom*1e12:.0f} pF")

    # gm/(2*pi*Cdom) is where the OPEN-loop gain reaches unity, not where the
    # LOOP gain does. The loop crosses 0 dB a factor of beta lower, beta being
    # the feedback division ratio, and it is the loop crossing that the phase
    # margin belongs to. Conflating the two is how an earlier revision of this
    # file came to report a "unity-loop-gain frequency" five times too high.
    rf, rg = 2200.0, 115.0
    beta = rg / (rf + rg)
    f_aol0 = gm / (2 * math.pi * cdom)
    print(f"Open-loop unity gain  : {f_aol0/1e6:.2f} MHz   (simulated 8.3 MHz)")
    print(f"Feedback factor beta  : {beta:.4f} (1/beta = {1/beta:.1f})")
    print(f"Unity-LOOP-gain freq  : {f_aol0*beta/1e3:.0f} kHz "
          f"(simulated 456 kHz)")

    # Slew rate is a capability here, not a limit: simulation shows the step
    # response is linear at full output, so the amplifier never reaches this.
    # See docs/02 section 2.3. Kept because if Cdom is ever raised this is the
    # number that says when it would start to matter.
    sr = i_tail / cdom
    vpk = (RAIL - VCE_SAT) / (1 + (RE / PAIRS_PER_CH) / min(LOADS.values()))
    sr_req = 2 * math.pi * 20e3 * vpk
    print(f"Slew capability       : {sr/1e6:.1f} V/us (Itail/Cdom)")
    print(f"Slew rate required    : {sr_req/1e6:.2f} V/us "
          f"(full output, 20 kHz) -> {sr/sr_req:.0f}x, never reached")

    print()
    rf, rg = 2200.0, 115.0
    print(f"Feedback network      : Rf {rf:.0f} / Rg {rg:.0f} -> "
          f"gain {1 + rf/rg:.1f} V/V ({20*math.log10(1+rf/rg):.1f} dB)")
    print(f"Input sensitivity for clipping: {vpk/math.sqrt(2)/(1+rf/rg):.3f} Vrms")
    r_par = rf * rg / (rf + rg)
    en_r = math.sqrt(4 * 1.38e-23 * 300 * r_par)
    print(f"Rf||Rg = {r_par:.1f} ohm -> thermal noise {en_r*1e9:.2f} nV/rtHz")
    en_total = math.sqrt(en_r ** 2 + (2.0e-9) ** 2 + (1.5e-9) ** 2)
    print(f"Estimated input-referred noise: {en_total*1e9:.2f} nV/rtHz")
    vn_out = en_total * (1 + rf / rg) * math.sqrt(22000)
    print(f"Output noise (22 kHz BW)      : {vn_out*1e6:.1f} uV rms")
    print(f"SNR ref {vpk/math.sqrt(2):.1f} Vrms          : "
          f"{20*math.log10(vpk/math.sqrt(2)/vn_out):.1f} dB")

    print()
    fp = 1 / (2 * math.pi * 100e3 * 2.2e-6)
    print(f"Input HPF: 2.2 uF film into 100k -> -3 dB at {fp:.2f} Hz")


def smps() -> None:
    section("4. SMPS: TRANSFORMER, DUTY CYCLE, DEVICE STRESS")
    fsw = 65e3
    t = 1 / fsw
    ae = 173e-6          # ETD44 effective core area, m^2
    b_swing = 0.30       # peak-to-peak flux swing, tesla
    np_half = 3          # turns per primary half
    print(f"Switching frequency  : {fsw/1e3:.0f} kHz  (period {t*1e6:.2f} us)")
    print(f"Core                 : ETD44, Ae = {ae*1e6:.0f} mm^2, "
          f"dB = {b_swing:.2f} T pk-pk")
    v_in_max = 15.0
    np_min = v_in_max * 0.5 * t / (ae * b_swing)
    print(f"Minimum primary turns at Vin {v_in_max:.1f} V, D=0.5: "
          f"{np_min:.2f} -> use {np_half} + {np_half}")
    b_actual = v_in_max * 0.5 * t / (ae * np_half)
    print(f"Actual flux swing at {v_in_max:.0f} V input: {b_actual:.3f} T pk-pk "
          f"(3C95 saturates ~0.4 T at 100 degC)")

    print()
    v_sec_needed = RAIL + 1.5   # rail + rectifier + choke drop
    for v_in, label in ((11.0, "cranking / worst case"),
                        (12.6, "engine off"),
                        (14.4, "charging")):
        ns = 8
        d = v_sec_needed / (2 * v_in * ns / np_half)
        print(f"Vin {v_in:>5.1f} V ({label:<22}): Ns={ns} -> "
              f"required duty {d:.3f} {'*** OVER 0.45 ***' if d > 0.45 else ''}")
    print(f"-> main secondary {8} + {8} turns, regulated by duty cycle")

    print()
    p_out = 250.0
    eff = 0.85
    for v_in in (11.0, 12.6, 14.4):
        i_in = p_out / eff / v_in
        print(f"Vin {v_in:>5.1f} V: input current {i_in:5.1f} A "
              f"for {p_out:.0f} W out at {eff*100:.0f}% efficiency")
    print(f"-> fuse each board at 30 A; two boards need 4 AWG feed + 60-80 A "
          f"main fuse")

    print()
    v_ds = 2 * 15.0
    print(f"MOSFET Vds stress: 2 x Vin = {v_ds:.0f} V plus leakage ringing")
    print(f"  -> 100 V device (IRFB4110) gives >2x margin, snubber still required")
    i_pri_rms = p_out / eff / 12.6 / math.sqrt(2)
    print(f"Primary switch RMS current (approx): {i_pri_rms:.1f} A per switch")
    print(f"  -> 2x IRFB4110 in parallel per side, Rds(on) 3.7 mohm nominal")

    print()
    l_choke = 33e-6
    i_rail = 250 / 2 / RAIL
    dv = i_rail * t / (2 * 4700e-6)
    print(f"Output filter: choke-input, L = {l_choke*1e6:.0f} uH per rail, "
          f"C = 4700 uF + 1 uF film")
    print(f"Average rail current at full power: {i_rail:.1f} A per rail")
    print(f"Ripple from reservoir alone: {dv*1e3:.1f} mV pk-pk at {fsw/1e3:.0f} kHz")


def traces() -> None:
    section("5. TRACE SIZING (IPC-2221)")

    def width_mm(current: float, dt: float, oz: float, external: bool) -> float:
        k = 0.048 if external else 0.024
        area_mil2 = (current / (k * dt ** 0.44)) ** (1 / 0.725)
        thickness_mil = 1.378 * oz
        return area_mil2 / thickness_mil * 0.0254

    print("Width in mm for a given current, temperature rise and copper weight.\n")
    currents = [1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 40]
    print(f"{'I (A)':>6} | {'2oz ext':>9} {'2oz ext':>9} | "
          f"{'1oz ext':>9} | {'1oz int':>9}")
    print(f"{'':>6} | {'dT=10C':>9} {'dT=20C':>9} | {'dT=20C':>9} | {'dT=20C':>9}")
    print("-" * 60)
    for i in currents:
        print(f"{i:>6} | {width_mm(i,10,2,True):>8.2f}  "
              f"{width_mm(i,20,2,True):>8.2f}  | "
              f"{width_mm(i,20,1,True):>8.2f}  | "
              f"{width_mm(i,20,1,False):>8.2f}")

    print()
    print("Resistance of 2 oz (70 um) copper:")
    rho = 1.72e-8
    for w in (2, 3, 5, 8, 10, 15):
        r_per_m = rho / (w * 1e-3 * 70e-6)
        print(f"  {w:>2} mm wide: {r_per_m*1e3:6.2f} mohm/m  "
              f"-> {r_per_m*0.1*1e3:5.2f} mohm per 100 mm  "
              f"-> {r_per_m*0.1*10*1e3:5.1f} mV drop at 10 A")


def net_classes(res: dict) -> None:
    section("6. NET CLASS ASSIGNMENT")
    vpk = res["_totals"]["vpk"]
    rows = [
        ("HV_RAIL_MAIN", "+/-24 V rail trunk, PSU entry to reservoirs",
         "30 A peak", "10.0 mm", "0.40 mm"),
        ("HV_RAIL_CH", "+/-24 V feed to one channel output stage",
         f"{res['midbass']['i_peak']:.1f} A peak", "5.0 mm", "0.40 mm"),
        ("SPKR_OUT", "output node, emitter resistors to terminal",
         f"{res['midbass']['i_peak']:.1f} A peak", "5.0 mm", "0.40 mm"),
        ("PWR_GND", "output stage and reservoir return",
         "30 A peak", "10.0 mm / pour", "0.40 mm"),
        ("SIG_GND", "front-end reference, star point only", "< 100 mA",
         "0.60 mm", "0.30 mm"),
        ("FE_RAIL", "+/-30 V front-end rail", "< 200 mA", "0.80 mm", "0.30 mm"),
        ("AUDIO_IN", "input receiver to gain stage", "signal",
         "0.35 mm", "0.30 mm"),
        ("FEEDBACK", "output Kelvin tap to Rf", "signal", "0.40 mm", "0.30 mm"),
        ("BASE_DRIVE", "driver/output base network", "< 500 mA",
         "0.80 mm", "0.30 mm"),
        ("GATE_SMPS", "MOSFET gate drive", "3 A pulse", "1.50 mm", "0.40 mm"),
        ("B_PLUS", "battery input, PSU board", "30 A cont", "15.0 mm + bar",
         "1.00 mm"),
    ]
    print(f"{'net class':<15}{'purpose':<44}{'current':<12}{'width':<16}{'clr'}")
    print("-" * 100)
    for name, purpose, current, width, clr in rows:
        print(f"{name:<15}{purpose:<44}{current:<12}{width:<16}{clr}")
    print()
    print(f"(Peak currents assume {vpk:.1f} V peak into the stated load.)")


def main() -> None:
    print("FS-3W FRONT-STAGE AMPLIFIER -- DESIGN CALCULATIONS")
    res = power_and_current()
    heatsink(res)
    front_end()
    smps()
    traces()
    net_classes(res)
    print()


if __name__ == "__main__":
    main()
