#!/usr/bin/env python3
"""Generate the FS-3W hierarchical KiCad schematics from channel_netlist.py.

    python3 tools/gen_schematic.py
    python3 tools/check_schematic.py

channel_netlist.py is the source of truth for one amplifier channel. This
script places that channel on a 1.27 mm grid, labels every pin, and draws
collision-checked wires for nets with two to four connections (docs/07 §7.4).
A stub-then-jog router keeps those wires off other pins; high-fanout nets stay
labels-only. The channel sheet is instantiated three times under fs3w-amp.kicad_sch.
Regulators, protection, interface and the PSU project are generated from the
same docs/BoM the channel was; they have no separate Python netlist yet.
"""

from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

import kicad_sch_api as ksa
from kicad_sch_api.core.schematic import Schematic
from kicad_sch_api.library.cache import get_symbol_cache

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel_netlist import (  # noqa: E402
    ALLOWED_SINGLE_PIN,
    COMPONENTS,
    HIER_PINS,
    NETLIST,
    Comp,
    check as check_netlist,
)

ROOT = Path(__file__).resolve().parents[1]
AMP = ROOT / "fs3w-amp"
PSU = ROOT / "fs3w-psu"
LIB_SYM = ROOT / "lib" / "FS3W.kicad_sym"
LIB_FP = ROOT / "lib" / "FS3W.pretty"

G = 1.27  # KiCad 50 mil grid, mm
PROJECT_AMP = "fs3w-amp"
PROJECT_PSU = "fs3w-psu"

# Dual-opamp pin numbers on Amplifier_Operational:Opamp_Dual / TL072 / OPA1642.
U2_PIN = {
    ("U2A", "IN-"): "2", ("U2A", "IN+"): "3", ("U2A", "OUT"): "1",
    ("U2B", "IN-"): "6", ("U2B", "IN+"): "5", ("U2B", "OUT"): "7",
    ("U2P", "V+"): "8", ("U2P", "V-"): "4",
}
U2_UNIT = {"U2A": 1, "U2B": 2, "U2P": 3}

HIER_SHAPE = {
    "IN_HOT": "input", "IN_COLD": "input",
    "SPK_OUT": "output",
    "VCC_MAIN": "input", "VEE_MAIN": "input",
    "VCC_FE": "input", "VEE_FE": "input",
    "VCC_15": "input", "VEE_15": "input",
    "SIG_GND": "passive", "PWR_GND": "passive",
    "DC_SENSE": "output", "I_SENSE": "output",
    "MUTE_CTL": "input",
}

CHANNELS = (
    ("CH1_TWEETER", "2", "tweeter 4 Ω"),
    ("CH2_MID", "3", "midrange 4 Ω"),
    ("CH3_MIDBASS", "4", "midbass 2 Ω"),
)

POWER_NETS = (
    "VCC_MAIN", "VEE_MAIN", "VCC_FE", "VEE_FE",
    "VCC_15", "VEE_15", "SIG_GND", "PWR_GND",
)

# Root-side rename of per-channel hierarchical pins. `{s}` is T/M/B.
CH_RENAME = {
    "IN_HOT": "IN_HOT_{s}",
    "IN_COLD": "IN_COLD_{s}",
    "SPK_OUT": "SPK_{s}",
    "DC_SENSE": "DC_SENSE_{s}",
    "I_SENSE": "I_SENSE_{s}",
}

REG_PINS = (
    ("AUX_POS", "input"), ("AUX_NEG", "input"),
    ("VCC_FE", "output"), ("VEE_FE", "output"),
    ("VCC_15", "output"), ("VEE_15", "output"),
    ("SIG_GND", "passive"), ("PWR_GND", "passive"),
    ("VCC_MAIN", "passive"), ("VEE_MAIN", "passive"),
)
PROT_PINS = (
    ("DC_SENSE_T", "input"), ("DC_SENSE_M", "input"), ("DC_SENSE_B", "input"),
    ("I_SENSE_T", "input"), ("I_SENSE_M", "input"), ("I_SENSE_B", "input"),
    ("MUTE_CTL", "output"),
    ("RELAY_T", "output"), ("RELAY_M", "output"), ("RELAY_B", "output"),
    ("SHUTDOWN", "output"), ("REMOTE", "input"),
    ("VCC_MAIN", "input"), ("VEE_MAIN", "input"),
    ("V_BATT", "input"), ("SIG_GND", "passive"), ("PWR_GND", "passive"),
)
IFACE_PINS = (
    ("IN_HOT_T", "output"), ("IN_COLD_T", "output"),
    ("IN_HOT_M", "output"), ("IN_COLD_M", "output"),
    ("IN_HOT_B", "output"), ("IN_COLD_B", "output"),
    ("SPK_T", "input"), ("SPK_M", "input"), ("SPK_B", "input"),
    ("VCC_MAIN", "output"), ("VEE_MAIN", "output"), ("PWR_GND", "passive"),
    ("AUX_POS", "output"), ("AUX_NEG", "output"),
    ("REMOTE", "output"), ("SHUTDOWN", "input"),
    ("SIG_GND", "passive"), ("V_BATT", "output"),
)


def uid(*parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def g(gx: float, gy: float) -> tuple[float, float]:
    return (gx * G, gy * G)


def snap(x: float, y: float) -> tuple[float, float]:
    return (round(x / G) * G, round(y / G) * G)


def lib_id(c: Comp) -> str:
    return c.lib_id


def setup_cache() -> None:
    cache = get_symbol_cache()
    cache.add_library_path(LIB_SYM)


def kicad_pin(c: Comp, pin: str) -> str:
    """Map a channel_netlist pin (name or number) to a KiCad pin number."""
    if (c.ref, pin) in U2_PIN:
        return U2_PIN[(c.ref, pin)]
    cache = get_symbol_cache()
    sym = cache.get_symbol(c.lib_id)
    if sym is None:
        raise KeyError(f"symbol {c.lib_id} not in cache (needed for {c.ref}.{pin})")
    numbers = {p.number for p in sym.pins}
    if pin in numbers:
        return pin
    for p in sym.pins:
        if p.name == pin:
            return p.number
    raise KeyError(f"{c.ref} ({c.lib_id}) has no pin {pin!r}; "
                   f"have {[(p.number, p.name) for p in sym.pins]}")


def sch_ref(c: Comp) -> str:
    """Schematic reference. Multi-unit U2A/B/P share U2."""
    if c.package_of == "U2":
        return "U2"
    return c.ref


# ---------------------------------------------------------------------------
# Channel placement. Grid units. Signal flows left → right.
# ---------------------------------------------------------------------------


def channel_positions() -> dict[str, tuple[float, float, float]]:
    """ref -> (x_mm, y_mm, rotation_deg). Rot 90 puts a 2-pin part on the x-axis."""
    p: dict[str, tuple[float, float, float]] = {}

    def put(ref: str, gx: float, gy: float, rot: float = 0) -> None:
        p[ref] = (*g(gx, gy), rot)

    # -- receiver ----------------------------------------------------------
    put("R1", 28, 32, 90)
    put("R2", 28, 48, 90)
    put("U1", 48, 40)
    put("R7", 48, 64, 90)
    put("C1", 64, 48)
    put("C2", 40, 20)
    put("C3", 48, 20)
    put("C4", 40, 64)
    put("C5", 56, 64)

    # -- gain trim ---------------------------------------------------------
    put("R3", 78, 32, 90)
    put("RV1", 92, 40)
    put("C6", 106, 32, 90)
    put("R4", 106, 52)
    put("R6", 118, 32, 90)
    put("C7", 118, 52)
    put("R5", 106, 68)
    put("Q16", 118, 68)

    # -- LTP ---------------------------------------------------------------
    put("Q1A", 140, 28)
    put("Q1B", 140, 48)
    put("R8", 154, 28)
    put("R9", 154, 48)
    put("Q2", 168, 38)
    put("R10", 168, 20)
    put("D1", 182, 20, 90)
    put("R11", 182, 52)
    put("C8", 182, 36)

    # -- current mirror ----------------------------------------------------
    put("Q3A", 204, 28)
    put("Q3B", 204, 48)
    put("R12", 218, 28)
    put("R13", 218, 48)

    # -- VAS ---------------------------------------------------------------
    put("Q4", 240, 28)
    put("R14", 240, 48)
    put("R18", 254, 28, 90)
    put("Q5", 272, 28)
    put("R15", 272, 48)
    put("C9", 254, 12)
    put("R16", 240, 12, 90)
    put("C10", 226, 12)
    put("Q6", 272, 68)
    put("R19", 256, 68)
    put("D2", 240, 68, 90)
    put("R20", 272, 88)
    put("C11", 256, 88)

    # -- bias spreader -----------------------------------------------------
    put("Q7", 304, 40)
    put("R21", 320, 24)
    put("RV2", 336, 40)
    put("R22", 320, 56)
    put("C12", 304, 64)
    put("D3", 320, 80, 90)

    # -- output triple -----------------------------------------------------
    put("Q8", 360, 24)
    put("Q9", 360, 72)
    put("R23", 376, 40)
    put("R24", 376, 88)
    put("Q10", 396, 24)
    put("Q11", 396, 72)
    put("R25", 412, 40)
    put("R26", 412, 88)
    put("R27", 428, 16, 90)
    put("R28", 428, 32, 90)
    put("R29", 428, 64, 90)
    put("R30", 428, 80, 90)
    put("Q12", 452, 16)
    put("Q13", 452, 32)
    put("Q14", 452, 64)
    put("Q15", 452, 80)
    put("R31", 476, 16, 90)
    put("R32", 476, 32, 90)
    put("R33", 476, 64, 90)
    put("R34", 476, 80, 90)

    # -- output network ----------------------------------------------------
    put("R35", 504, 40, 90)
    put("C13", 520, 56)
    put("L1", 536, 40, 90)
    put("R36", 536, 64, 90)

    # -- feedback + servo (below the front end) ----------------------------
    put("R37", 360, 120, 90)
    put("R38", 376, 136)
    put("C14", 360, 104)
    put("R43", 396, 120, 90)
    put("R50", 476, 104, 90)
    put("R44", 140, 120, 90)
    put("U2A", 164, 120)
    put("C15", 164, 144)
    put("R45", 148, 144)
    put("R46", 188, 120, 90)
    put("U2B", 212, 120)
    put("R47", 228, 120)
    put("C16", 228, 136)
    put("R49", 212, 144)
    put("R48", 248, 120, 90)
    put("U2P", 188, 160)
    put("C17", 172, 160)
    put("C18", 204, 160)

    # -- local decoupling (right column) -----------------------------------
    put("C19", 560, 24)
    put("C20", 560, 48)
    put("C21", 576, 24)
    put("C22", 576, 48)
    put("C23", 560, 80)
    put("C24", 560, 104)
    put("C25", 576, 80)
    put("C26", 576, 104)

    missing = [c.ref for c in COMPONENTS if c.ref not in p]
    if missing:
        raise RuntimeError(f"channel placement missing refs: {missing}")
    return p


def new_sch(name: str, paper: str, ident: str) -> Schematic:
    sch = Schematic.create(name, paper=paper, uuid=uid(ident), generator="fs3w-gen_schematic")
    sch.name = name
    return sch


def add_comp(sch: Schematic, c: Comp, pos: tuple[float, float, float],
             unit: int = 1) -> object:
    x, y, rot = pos
    props = {}
    if c.dnp:
        props["DNP"] = "1"
    if c.desc:
        props["Description"] = c.desc[:80]
    if c.tolerance:
        props["Tolerance"] = c.tolerance
    comp = sch.components.add(
        lib_id=c.lib_id,
        reference=sch_ref(c),
        value=c.value,
        position=(x, y),
        footprint=c.footprint,
        unit=unit,
        rotation=rot,
        component_uuid=uid("sym", sch.name, sch_ref(c), str(unit)),
        **props,
    )
    if c.package_of == "U2" and unit != 1:
        comp._data.in_bom = False
    return comp


def pin_pos(comp, number: str):
    """Absolute pin position in schematic space (Y-down).

    Component.get_pin_position skips the symbol→schematic Y flip, so labels
    land on the opposite pin of every vertical part. Use apply_transformation.

    kicad-sch-api's 90°/270° (written for Y-up math after the flip) is the
    opposite of KiCad 10's schematic rotation, which is why every rotated
    2-pin part was attaching the label to the other end.
    """
    from kicad_sch_api.core.geometry import apply_transformation
    from kicad_sch_api.core.types import Point
    pin = comp.get_pin(number)
    if pin is None:
        raise KeyError(f"{comp.reference} pin {number} has no position")
    rot = comp.rotation % 360
    if rot == 90:
        rot = 270
    elif rot == 270:
        rot = 90
    x, y = apply_transformation(
        (pin.position.x, pin.position.y),
        comp.position,
        rot,
        None,
    )
    return Point(x, y)


def add_local_label(sch: Schematic, text: str, pos, rotation: float = 0) -> None:
    x, y = snap(pos.x, pos.y)
    sch.add_label(text, position=(x, y), rotation=rotation)


def add_hier_label(sch: Schematic, text: str, pos, shape: str, rotation: float = 0) -> None:
    x, y = snap(pos.x, pos.y)
    sch.add_hierarchical_label(text, (x, y), shape=shape, rotation=rotation)
    # kicad-sch-api omits shape in the sync dict; patch it.
    for hl in sch._data.get("hierarchical_labels", []):
        if hl.get("text") == text and abs(hl["position"]["x"] - x) < 0.02:
            hl["shape"] = shape


def add_nc(sch: Schematic, pos) -> None:
    sch.no_connects.add(position=(snap(pos.x, pos.y)))


# ---------------------------------------------------------------------------
# Collision-checked wiring (2–4 pin nets)
# ---------------------------------------------------------------------------

STUB = 2.54
HIT_R = 0.64  # mm; half a 1.27 grid, so a pin-column scrape is a hit


def _xy(pt) -> tuple[float, float]:
    return (float(pt.x), float(pt.y))


def _outward(comp, pt) -> tuple[float, float]:
    dx = pt.x - comp.position.x
    dy = pt.y - comp.position.y
    if abs(dx) >= abs(dy):
        return (1.0 if dx >= 0 else -1.0, 0.0)
    return (0.0, 1.0 if dy >= 0 else -1.0)


def _seg_hits(a: tuple[float, float], b: tuple[float, float],
              obstacles: list[tuple[float, float]],
              ignore: list[tuple[float, float]]) -> bool:
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    length = (vx * vx + vy * vy) ** 0.5
    if length < 1e-6:
        return False
    for ox, oy in obstacles:
        if any(abs(ox - ix) < 0.3 and abs(oy - iy) < 0.3 for ix, iy in ignore):
            continue
        t = max(0.0, min(1.0, ((ox - ax) * vx + (oy - ay) * vy) / (length * length)))
        px, py = ax + t * vx, ay + t * vy
        if (ox - px) ** 2 + (oy - py) ** 2 < HIT_R * HIT_R:
            return True
    return False


def _path_clear(points: list[tuple[float, float]],
                obstacles: list[tuple[float, float]],
                ignore: list[tuple[float, float]]) -> bool:
    for i in range(len(points) - 1):
        if _seg_hits(points[i], points[i + 1], obstacles, ignore):
            return False
    return True


def _draw_path(sch: Schematic, points: list[tuple[float, float]]) -> None:
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if abs(a[0] - b[0]) < 0.02 and abs(a[1] - b[1]) < 0.02:
            continue
        sch.add_wire(a, b, grid_units=False)


def route_pair(sch: Schematic, comp_a, pt_a, comp_b, pt_b,
               obstacles: list[tuple[float, float]]) -> bool:
    """Wire two pins via an outward stub so the jog misses a pin column."""
    a, b = _xy(pt_a), _xy(pt_b)
    da, db = _outward(comp_a, pt_a), _outward(comp_b, pt_b)
    sa = (a[0] + da[0] * STUB, a[1] + da[1] * STUB)
    sb = (b[0] + db[0] * STUB, b[1] + db[1] * STUB)
    sa2 = (sa[0] + da[0] * STUB, sa[1] + da[1] * STUB)
    sb2 = (sb[0] + db[0] * STUB, sb[1] + db[1] * STUB)
    ignore = [a, b]
    paths: list[list[tuple[float, float]]] = []
    if abs(a[0] - b[0]) < 0.05 or abs(a[1] - b[1]) < 0.05:
        paths.append([a, b])
    paths.append([a, sa, sb, b])
    if abs(sa[0] - sb[0]) > 0.05 and abs(sa[1] - sb[1]) > 0.05:
        paths.append([a, sa, (sb[0], sa[1]), sb, b])
        paths.append([a, sa, (sa[0], sb[1]), sb, b])
        paths.append([a, sa, sa2, (sb2[0], sa2[1]), sb2, sb, b])
        paths.append([a, sa, sa2, (sa2[0], sb2[1]), sb2, sb, b])
    for path in paths:
        if _path_clear(path, obstacles, ignore):
            _draw_path(sch, path)
            return True
    return False


def wire_channel_nets(sch: Schematic, by_ref: dict, nets: dict[str, list[tuple[str, str]]],
                      pin_pts: dict[tuple[str, str], object]) -> None:
    """Wire 2–4 connection nets. Larger nets stay labels-only (docs/07)."""
    by_c = {c.ref: c for c in COMPONENTS}
    all_pts = [(_xy(pt)) for pt in pin_pts.values()]
    wired = 0
    skipped = 0
    for net, conns in nets.items():
        if net in ALLOWED_SINGLE_PIN or len(conns) < 2 or len(conns) > 4:
            continue
        nodes = []
        for ref, pin in conns:
            kn = kicad_pin(by_c[ref], pin)
            nodes.append((by_ref[ref], pin_pts[(ref, kn)], ref, kn))
        # MST on Manhattan distance
        edges: list[tuple[float, int, int]] = []
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                ai, bi = _xy(nodes[i][1]), _xy(nodes[j][1])
                edges.append((abs(ai[0] - bi[0]) + abs(ai[1] - bi[1]), i, j))
        edges.sort()
        parent = list(range(len(nodes)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for _, i, j in edges:
            ri, rj = find(i), find(j)
            if ri == rj:
                continue
            parent[ri] = rj
            ca, pa, *_ = nodes[i]
            cb, pb, *_ = nodes[j]
            # Obstacles: pins that are not on this net
            ignore_pts = {_xy(n[1]) for n in nodes}
            obstacles = [p for p in all_pts if p not in ignore_pts]
            if route_pair(sch, ca, pa, cb, pb, obstacles):
                wired += 1
            else:
                skipped += 1
    print(f"  wired {wired} segments, {skipped} left as labels-only")


def build_channel() -> Schematic:
    sch = new_sch("AMP_CHANNEL", "A1", "amp_channel")
    pos = channel_positions()
    by_ref: dict[str, object] = {}

    for c in COMPONENTS:
        unit = U2_UNIT.get(c.ref, 1)
        by_ref[c.ref] = add_comp(sch, c, pos[c.ref], unit=unit)

    # Cluster titles
    titles = [
        (24, 8, "RECEIVER  INA1651"),
        (78, 8, "TRIM"),
        (140, 8, "LTP"),
        (200, 8, "MIRROR"),
        (240, 4, "VAS"),
        (304, 8, "SPREADER"),
        (360, 6, "EF3 OUTPUT"),
        (504, 8, "ZOBEL / L"),
        (140, 104, "DC SERVO"),
        (552, 8, "DECOUPLING"),
    ]
    for gx, gy, text in titles:
        sch.add_text(text, g(gx, gy), size=2.54)

    # Hierarchical labels sit on a pin of that net (a disconnected column
    # is ERC-dangling and does not join the local labels).
    nets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ref, pin, net in NETLIST:
        nets[net].append((ref, pin))

    pin_pts: dict[tuple[str, str], object] = {}
    for net, conns in nets.items():
        if net in ALLOWED_SINGLE_PIN:
            ref, pin = conns[0]
            n = kicad_pin(next(c for c in COMPONENTS if c.ref == ref), pin)
            add_nc(sch, pin_pos(by_ref[ref], n))
            continue
        hier_done = False
        for ref, pin in conns:
            c = next(x for x in COMPONENTS if x.ref == ref)
            n = kicad_pin(c, pin)
            pt = pin_pos(by_ref[ref], n)
            pin_pts[(ref, n)] = pt
            if net in HIER_PINS and not hier_done:
                add_hier_label(sch, net, pt, HIER_SHAPE.get(net, "passive"))
                hier_done = True
            else:
                add_local_label(sch, net, pt)

    # INA1651 NC pins 5–9 (also obstacles for the router)
    u1 = by_ref["U1"]
    for n in ("5", "6", "7", "8", "9"):
        pt = pin_pos(u1, n)
        pin_pts[("U1", n)] = pt
        add_nc(sch, pt)

    wire_channel_nets(sch, by_ref, nets, pin_pts)
    return sch


# ---------------------------------------------------------------------------
# Supporting sheets
# ---------------------------------------------------------------------------


def _part(sch, lib, ref, value, gx, gy, footprint="", rot=0, unit=1):
    return sch.components.add(
        lib_id=lib, reference=ref, value=value,
        position=g(gx, gy), footprint=footprint or None,
        rotation=rot, unit=unit,
        component_uuid=uid("sym", sch.name, ref, str(unit)),
    )


def _lab(sch, text, gx, gy, hier=False, shape="passive"):
    if hier:
        add_hier_label(sch, text, type("P", (), {"x": g(gx, gy)[0], "y": g(gx, gy)[1]})(), shape)
    else:
        sch.add_label(text, position=g(gx, gy))


_FLAG_N = 0


def _pwr_flag(sch, net, gx, gy):
    global _FLAG_N
    _FLAG_N += 1
    sch.components.add(
        lib_id="power:PWR_FLAG", reference=f"#FLG{_FLAG_N:02d}", value="PWR_FLAG",
        position=g(gx, gy), component_uuid=uid("flag", sch.name, net, str(_FLAG_N)),
    )
    sch.add_label(net, position=g(gx, gy))


def build_regulators() -> Schematic:
    sch = new_sch("REGULATORS", "A3", "regulators")
    sch.add_text("±30 V (LM317/337 from aux) and ±15 V (from ±30 V)", g(20, 10), size=2.54)

    for i, (n, sh) in enumerate(REG_PINS):
        _lab(sch, n, 8, 20 + 8 * i, hier=True, shape=sh)

    # +30 V
    _part(sch, "Regulator_Linear:LM317_TO-220", "U403", "LM317TG", 50, 40,
          "Package_TO_SOT_THT:TO-220-3_Vertical")
    _part(sch, "Device:R", "R401", "240R", 70, 40, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:R", "R402", "5k62", 80, 52, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:C_Polarized", "C403", "220u/63V", 70, 24,
          "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm")
    _lab(sch, "AUX_POS", 40, 40)
    _lab(sch, "VCC_FE", 90, 40)
    _lab(sch, "SIG_GND", 80, 64)

    # -30 V
    _part(sch, "Regulator_Linear:LM337_TO220", "U404", "LM337TG", 50, 100,
          "Package_TO_SOT_THT:TO-220-3_Vertical")
    _part(sch, "Device:R", "R403", "240R", 70, 100, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:R", "R404", "5k62", 80, 112, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:C_Polarized", "C404", "220u/63V", 70, 84,
          "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm")
    _lab(sch, "AUX_NEG", 40, 100)
    _lab(sch, "VEE_FE", 90, 100)
    _lab(sch, "SIG_GND", 80, 124)

    # +15 V from +30 V
    _part(sch, "Regulator_Linear:LM317_TO-220", "U405", "LM317TG", 140, 40,
          "Package_TO_SOT_THT:TO-220-3_Vertical")
    _part(sch, "Device:R", "R405", "240R", 160, 40, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:R", "R406", "2k67", 170, 52, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:C", "C405", "10u/50V", 160, 24, "Capacitor_SMD:C_0805_2012Metric")
    _lab(sch, "VCC_FE", 128, 40)
    _lab(sch, "VCC_15", 180, 40)
    _lab(sch, "SIG_GND", 170, 64)

    # -15 V from -30 V
    _part(sch, "Regulator_Linear:LM337_TO220", "U406", "LM337TG", 140, 100,
          "Package_TO_SOT_THT:TO-220-3_Vertical")
    _part(sch, "Device:R", "R407", "240R", 160, 100, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:R", "R408", "2k67", 170, 112, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:C", "C406", "10u/50V", 160, 84, "Capacitor_SMD:C_0805_2012Metric")
    _lab(sch, "VEE_FE", 128, 100)
    _lab(sch, "VEE_15", 180, 100)
    _lab(sch, "SIG_GND", 170, 124)

    # Main-rail bulk on the amp board (BoM C401/C402)
    _part(sch, "Device:C_Polarized", "C401", "4700u/35V", 50, 160,
          "Capacitor_THT:CP_Radial_D18.0mm_P7.50mm")
    _part(sch, "Device:C_Polarized", "C402", "4700u/35V", 80, 160,
          "Capacitor_THT:CP_Radial_D18.0mm_P7.50mm")
    _lab(sch, "VCC_MAIN", 50, 148)
    _lab(sch, "PWR_GND", 50, 172)
    _lab(sch, "VEE_MAIN", 80, 148)
    _lab(sch, "PWR_GND", 80, 172)
    return sch


def build_protection() -> Schematic:
    """Detectors, latch, sequencing, relays. G4A footprint is still TBD."""
    sch = new_sch("PROTECTION", "A3", "protection")
    sch.add_text("Protection / sequencing — see docs/04. Relay footprint G4A not yet drawn.",
                 g(16, 10), size=2.0)

    for i, (n, sh) in enumerate(PROT_PINS):
        _lab(sch, n, 8, 18 + 6 * i, hier=True, shape=sh)

    # Two LM339 quads
    _part(sch, "Comparator:LM339", "U401", "LM339", 70, 50, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=1)
    _part(sch, "Comparator:LM339", "U401", "LM339", 100, 50, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=2)
    _part(sch, "Comparator:LM339", "U401", "LM339", 130, 50, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=3)
    _part(sch, "Comparator:LM339", "U401", "LM339", 160, 50, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=4)
    _part(sch, "Comparator:LM339", "U401", "LM339", 190, 50, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=5)
    _part(sch, "Comparator:LM339", "U402", "LM339", 70, 90, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=1)
    _part(sch, "Comparator:LM339", "U402", "LM339", 100, 90, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=2)
    _part(sch, "Comparator:LM339", "U402", "LM339", 130, 90, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=3)
    _part(sch, "Comparator:LM339", "U402", "LM339", 160, 90, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=4)
    _part(sch, "Comparator:LM339", "U402", "LM339", 190, 90, "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=5)

    for net, gx, gy in (
        ("V_BATT", 70, 30), ("SIG_GND", 100, 30),
        ("DC_SENSE_T", 70, 70), ("DC_SENSE_M", 100, 70), ("DC_SENSE_B", 130, 70),
        ("I_SENSE_T", 70, 110), ("I_SENSE_M", 100, 110), ("I_SENSE_B", 130, 110),
        ("VCC_MAIN", 160, 70), ("VEE_MAIN", 190, 70),
        ("REMOTE", 160, 110), ("SHUTDOWN", 190, 110),
        ("MUTE_CTL", 220, 50),
    ):
        _lab(sch, net, gx, gy)

    # Relays — symbol only; G4A footprint waits on a traced drawing (DEVIATIONS.md).
    for i, (ref, net) in enumerate((("K401", "RELAY_T"), ("K402", "RELAY_M"), ("K403", "RELAY_B"))):
        _part(sch, "Relay:Relay_SPST-NO", ref, "G4A-1A-PE DC12", 70 + 40 * i, 150)
        _lab(sch, net, 70 + 40 * i, 138)
        _lab(sch, "V_BATT", 62 + 40 * i, 138)
        _lab(sch, "SPK_" + "TMB"[i], 78 + 40 * i, 162)
        _lab(sch, "PWR_GND", 62 + 40 * i, 162)

    _part(sch, "Device:Thermistor_NTC", "RT401", "10k NTC", 210, 150)
    _part(sch, "Switch:SW_SPST", "S401", "100C NC", 240, 150)
    _lab(sch, "SIG_GND", 210, 162)
    _lab(sch, "V_BATT", 240, 138)

    for ref, val, gx in (("D401", "LED_GN", 70), ("D402", "LED_AM", 90), ("D403", "LED_RD", 110)):
        _part(sch, "Device:LED", ref, val, gx, 180, "LED_THT:LED_D3.0mm")
        _lab(sch, "V_BATT", gx, 172)
        _lab(sch, "SIG_GND", gx, 188)

    return sch


def build_interface() -> Schematic:
    sch = new_sch("INTERFACE", "A3", "interface")
    sch.add_text("Board edge: inputs, speakers, PSU entry, remote / shutdown", g(16, 10), size=2.54)

    for i, (n, sh) in enumerate(IFACE_PINS):
        _lab(sch, n, 8, 18 + 6 * i, hier=True, shape=sh)

    for i, (ref, hot, cold) in enumerate((
        ("J401", "IN_HOT_T", "IN_COLD_T"),
        ("J402", "IN_HOT_M", "IN_COLD_M"),
        ("J403", "IN_HOT_B", "IN_COLD_B"),
    )):
        _part(sch, "Connector_Generic:Conn_01x02", ref, "TB003-500-02BE",
              50, 30 + 24 * i,
              "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal")
        _lab(sch, hot, 62, 30 + 24 * i)
        _lab(sch, cold, 62, 36 + 24 * i)

    for i, (ref, spk) in enumerate((("J404", "SPK_T"), ("J405", "SPK_M"), ("J406", "SPK_B"))):
        _part(sch, "Connector_Generic:Conn_01x02", ref, "TB006-508-02BE",
              110, 30 + 24 * i,
              "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal")
        _lab(sch, spk, 122, 30 + 24 * i)
        _lab(sch, "PWR_GND", 122, 36 + 24 * i)

    _part(sch, "Connector_Generic:Conn_01x03", "J407", "TB007-762-03BE",
          50, 120,
          "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal")
    _lab(sch, "VCC_MAIN", 64, 120)
    _lab(sch, "PWR_GND", 64, 126)
    _lab(sch, "VEE_MAIN", 64, 132)

    _part(sch, "Connector_Generic:Conn_01x02", "J408", "REMOTE",
          110, 120, "Connector_Molex:Molex_KK-254_AE-6410-02A_1x02_P2.54mm_Vertical")
    _lab(sch, "REMOTE", 122, 120)
    _lab(sch, "SIG_GND", 122, 126)
    _part(sch, "Connector_Generic:Conn_01x02", "J409", "SHUTDOWN",
          110, 144, "Connector_Molex:Molex_KK-254_AE-6410-02A_1x02_P2.54mm_Vertical")
    _lab(sch, "SHUTDOWN", 122, 144)
    _lab(sch, "SIG_GND", 122, 150)

    _part(sch, "Connector_Generic:Conn_01x04", "J410", "AUX",
          50, 156, "Connector_Molex:Molex_KK-254_AE-6410-04A_1x04_P2.54mm_Vertical")
    _lab(sch, "AUX_POS", 64, 156)
    _lab(sch, "AUX_NEG", 64, 162)
    _lab(sch, "SIG_GND", 64, 168)
    _lab(sch, "V_BATT", 64, 174)
    return sch


def build_psu() -> Schematic:
    sch = new_sch("FS3W_PSU", "A2", "psu")
    sch.add_text("Regulated push-pull SMPS — docs/03. Rt/Ct measured, not calculated.",
                 g(16, 8), size=2.54)

    # Input
    _part(sch, "Device:Fuse", "F10", "30A ATO", 30, 40, "FS3W:Fuse_ATO_Blade", 90)
    _part(sch, "Device:D_TVS", "D24", "SMDJ30CA", 50, 40, "Diode_SMD:D_SMC")
    _part(sch, "Device:D_TVS", "D25", "SMCJ33A", 70, 40, "Diode_SMD:D_SMC")
    _part(sch, "Transistor_FET:Q_NMOS_GDS", "Q24", "IRFB4110", 90, 40,
          "FS3W:TO-220-3_Vertical_HeatsinkWall")
    _part(sch, "Device:L", "L23", "CM 25uH", 110, 40, "Inductor_THT:L_Toroid_Vertical_D21.6mm_P9.00mm")
    _part(sch, "Device:C_Polarized", "C30", "4700u/25V", 130, 32,
          "Capacitor_THT:CP_Radial_D18.0mm_P7.50mm")
    _part(sch, "Device:C_Polarized", "C31", "4700u/25V", 146, 32,
          "Capacitor_THT:CP_Radial_D18.0mm_P7.50mm")
    _lab(sch, "BPLUS", 20, 40)
    _lab(sch, "SMPS_GND", 50, 56)
    _lab(sch, "VIN", 160, 40)

    # Controller
    _part(sch, "FS3W:SG3525A", "U10", "SG3525ADWR2G", 60, 100,
          "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm")
    _part(sch, "Device:C", "C55", "10n C0G Ct", 40, 120, "Capacitor_SMD:C_0805_2012Metric")
    _part(sch, "Device:R", "R73", "Rt TBD", 28, 120, "Resistor_SMD:R_0805_2012Metric")
    _part(sch, "Device:C", "C54", "10u SS", 40, 136, "Capacitor_SMD:C_0805_2012Metric")
    _lab(sch, "VIN", 60, 80)
    _lab(sch, "SMPS_GND", 60, 120)
    _lab(sch, "SHUTDOWN", 80, 80)
    _lab(sch, "SYNC", 40, 80)
    _lab(sch, "GATE_A", 80, 112)
    _lab(sch, "GATE_B", 80, 104)

    # Gate driver + MOSFETs
    _part(sch, "Driver_FET:UCC27524D", "U11", "UCC27524ADR", 120, 100,
          "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
    for i, ref in enumerate(("Q20", "Q21", "Q22", "Q23")):
        _part(sch, "Transistor_FET:Q_NMOS_GDS", ref, "IRFB4110",
              160 + 20 * i, 100, "FS3W:TO-220-3_Vertical_HeatsinkWall")
        _part(sch, "Device:R", f"R{61+i}", "4R7", 160 + 20 * i, 84,
              "Resistor_SMD:R_1206_3216Metric", 90)
        _lab(sch, "GATE_A" if i < 2 else "GATE_B", 160 + 20 * i, 76)
        _lab(sch, "SMPS_GND", 160 + 20 * i, 116)
        _lab(sch, "T1_PRI_A" if i < 2 else "T1_PRI_B", 168 + 20 * i, 100)

    # Transformer (one physical ETD44; two symbols so the windings are reviewable)
    _part(sch, "Device:Transformer_1P_2S", "T1A", "ETD44 main", 80, 160, "FS3W:XFMR_ETD44")
    _part(sch, "Device:Transformer_1P_2S", "T1B", "ETD44 aux", 120, 160, "FS3W:XFMR_ETD44")
    _lab(sch, "T1_PRI_A", 70, 152)
    _lab(sch, "T1_PRI_B", 70, 168)
    _lab(sch, "SMPS_GND", 90, 176)
    _lab(sch, "SEC_POS", 100, 152)
    _lab(sch, "SEC_NEG", 100, 168)
    _lab(sch, "AUX_POS", 140, 152)
    _lab(sch, "AUX_NEG", 140, 168)

    # Output
    _part(sch, "Device:D_Schottky", "D20", "STPS40H100CW", 180, 152,
          "FS3W:TO-247-3_Vertical_HeatsinkWall")
    _part(sch, "Device:D_Schottky", "D21", "STPS40H100CW", 180, 176,
          "FS3W:TO-247-3_Vertical_HeatsinkWall")
    _part(sch, "Device:L", "L20", "33u coupled", 210, 160,
          "Inductor_THT:L_Toroid_Vertical_D28.0mm_P12.70mm", 90)
    _part(sch, "Device:C_Polarized", "C38", "4700u/35V", 240, 148,
          "Capacitor_THT:CP_Radial_D18.0mm_P7.50mm")
    _part(sch, "Device:C_Polarized", "C39", "4700u/35V", 240, 176,
          "Capacitor_THT:CP_Radial_D18.0mm_P7.50mm")
    _lab(sch, "VCC_MAIN", 260, 148)
    _lab(sch, "VEE_MAIN", 260, 176)
    _lab(sch, "PWR_GND", 240, 164)

    for net, gx, gy in (
        ("VCC_MAIN", 280, 40), ("VEE_MAIN", 300, 40), ("PWR_GND", 320, 40),
        ("AUX_POS", 280, 56), ("AUX_NEG", 300, 56), ("SMPS_GND", 320, 56),
        ("VIN", 280, 72), ("BPLUS", 300, 72),
    ):
        _pwr_flag(sch, net, gx, gy)

    _part(sch, "Connector_Generic:Conn_01x02", "J13", "SYNC", 40, 200,
          "Connector_Molex:Molex_KK-254_AE-6410-02A_1x02_P2.54mm_Vertical")
    _lab(sch, "SYNC", 52, 200)
    _lab(sch, "SMPS_GND", 52, 206)
    return sch


# ---------------------------------------------------------------------------
# Root, project files, instances
# ---------------------------------------------------------------------------


def write_lib_tables(folder: Path) -> None:
    rel_sym = os_rel(folder, LIB_SYM)
    rel_fp = os_rel(folder, LIB_FP)
    (folder / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n'
        f'  (lib (name "FS3W")(type "KiCad")(uri "{rel_sym}")'
        '(options "")(descr "FS-3W custom symbols"))\n)\n',
        encoding="utf-8",
    )
    (folder / "fp-lib-table").write_text(
        '(fp_lib_table\n  (version 7)\n'
        f'  (lib (name "FS3W")(type "KiCad")(uri "{rel_fp}")'
        '(options "")(descr "FS-3W custom footprints"))\n)\n',
        encoding="utf-8",
    )


def os_rel(from_dir: Path, target: Path) -> str:
    return "${KIPRJMOD}/" + os_relpath(target, from_dir)


def os_relpath(target: Path, start: Path) -> str:
    return Path(os_rel_str(target, start)).as_posix()


def os_rel_str(target: Path, start: Path) -> str:
    import os
    return os.path.relpath(target, start)


def write_pro(folder: Path, name: str, sheets: list[tuple[str, str]]) -> None:
    """Minimal KiCad 10 project file."""
    import json
    sheet_entries = [[uid, title] for uid, title in sheets]
    pro = {
        "board": {
            "3dviewports": [],
            "design_settings": {"defaults": {}},
            "ipc2581": {},
            "layer_presets": [],
            "viewports": [],
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "erc": {"erc_exclusions": [], "meta": {"version": 0}, "pin_map": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": ["FS3W"]},
        "meta": {"filename": f"{name}.kicad_pro", "version": 3},
        "net_settings": {"classes": [], "meta": {"version": 4}},
        "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
        "schematic": {
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            "spice_current_sheet_as_root": False,
            "spice_save_all_currents": False,
            "spice_save_all_voltages": False,
        },
        "sheets": sheet_entries,
        "text_variables": {},
    }
    (folder / f"{name}.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n", encoding="utf-8")


def annotate_ref(ref: str, channel: int) -> str:
    """R1 → R101, Q1A → Q101A, U2 → U102, RV1 → RV101."""
    import re
    m = re.match(r"^([A-Z]+)(\d+)(.*)$", ref)
    if not m:
        return ref
    return f"{m.group(1)}{channel}{int(m.group(2)):02d}{m.group(3)}"


def rewrite_channel_instances(path: Path, root_uuid: str,
                              sheets: list[tuple[str, int]]) -> None:
    """Give each channel instance unique refs (R101 / R201 / R301)."""
    import re
    text = path.read_text(encoding="utf-8")
    # lib_symbols also contain (property "Reference" "R"); only rewrite
    # placed symbols, which start with (symbol / (lib_id ...).
    marker = "\n\t(symbol\n\t\t(lib_id"
    idx = text.find(marker)
    if idx < 0:
        print("  WARN  no placed symbols found to annotate")
        return
    head, body = text[:idx], text[idx:]

    inst_re = re.compile(
        r'\(instances\s+\(project "[^"]+"\s+'
        r'\(path "/[^"]+"\s+'
        r'\(reference "[^"]+"\)\s+'
        r'\(unit (\d+)\)\s*\)\s*\)\s*\)',
        re.S,
    )
    ref_re = re.compile(r'\(property "Reference" "([^"]+)"')
    n = 0
    chunks = re.split(r'(?=\n\t\(symbol\n\t\t\(lib_id)', body)
    out = []
    for chunk in chunks:
        if not chunk.strip():
            out.append(chunk)
            continue
        rm = ref_re.search(chunk)
        if not rm:
            out.append(chunk)
            continue
        ref = rm.group(1)
        um = inst_re.search(chunk)
        if not um:
            out.append(chunk)
            continue
        unit = um.group(1)
        paths = "\n".join(
            f'        (path "/{root_uuid}/{sheet_uuid}"\n'
            f'          (reference "{annotate_ref(ref, ch)}")\n'
            f'          (unit {unit})\n'
            f'        )'
            for sheet_uuid, ch in sheets
        )
        new_inst = (
            f'(instances\n      (project "{PROJECT_AMP}"\n'
            + paths
            + "\n      )\n    )"
        )
        chunk = inst_re.sub(new_inst, chunk, count=1)
        n += 1
        out.append(chunk)
    path.write_text(head + "".join(out), encoding="utf-8")
    print(f"  rewrote {n} symbol instance blocks for R1xx/R2xx/R3xx")


def sheet_pin_xy(pos: tuple[float, float], size: tuple[float, float],
                 edge: str, along: float) -> tuple[float, float]:
    """Match kicad-sch-api SheetManager.add_sheet_pin coordinate convention."""
    sx, sy = pos
    sw, sh = size
    if edge == "right":
        return (sx + sw, sy + along)
    if edge == "bottom":
        return (sx + along, sy + sh)
    if edge == "left":
        return (sx, sy + sh - along)
    if edge == "top":
        return (sx + along, sy)
    raise ValueError(edge)


def split_edges(n: int, height: float, n_left: int | None = None,
                margin: float = 5.08) -> list[tuple[str, float]]:
    """Evenly space n pins on left then right; along is from the edge origin."""
    n_left = n_left if n_left is not None else (n + 1) // 2
    n_right = n - n_left

    def spreads(count: int) -> list[float]:
        if count <= 0:
            return []
        if count == 1:
            return [height / 2]
        span = max(height - 2 * margin, margin)
        return [margin + i * span / (count - 1) for i in range(count)]

    return [("left", a) for a in spreads(n_left)] + [("right", a) for a in spreads(n_right)]


def add_sheet_pins(sch: Schematic, sheet_uuid: str,
                   pos: tuple[float, float], size: tuple[float, float],
                   pins: list[tuple[str, str, str, float]],
                   rename: dict[str, str] | None = None) -> None:
    """Add hierarchical sheet pins and a local label sitting on each pin."""
    rename = rename or {}
    for name, shape, edge, along in pins:
        sch.add_sheet_pin(sheet_uuid, name, shape, edge, along)
        x, y = sheet_pin_xy(pos, size, edge, along)
        sch.add_label(rename.get(name, name), position=(x, y))


def build_root(channel_uuid: str) -> tuple[Schematic, str, list[tuple[str, int]]]:
    sch = new_sch(PROJECT_AMP, "A2", "amp_root")
    root_uuid = sch._data["uuid"]
    sheet_meta: list[tuple[str, int]] = []

    ch_size = g(70, 90)
    for i, (name, page, note) in enumerate(CHANNELS):
        su = uid("sheet", name)
        sheet_meta.append((su, i + 1))
        pos = g(20 + i * 90, 20)
        sch.add_sheet(
            name=name, filename="amp_channel.kicad_sch",
            position=pos, size=ch_size,
            project_name=PROJECT_AMP, page_number=page, uuid=su,
        )
        suffix = "TMB"[i]
        rename = {pin: tmpl.format(s=suffix) for pin, tmpl in CH_RENAME.items()}
        pins = []
        for j, pin in enumerate(HIER_PINS):
            edge = "left" if j < 8 else "right"
            along = (8 + (j % 8) * 10) * G
            pins.append((pin, HIER_SHAPE.get(pin, "passive"), edge, along))
        add_sheet_pins(sch, su, pos, ch_size, pins, rename)
        sch.add_text(note, g(22 + i * 90, 112), size=1.5)

    ru, pu, iu = uid("sheet", "REGULATORS"), uid("sheet", "PROTECTION"), uid("sheet", "INTERFACE")
    blocks = (
        (ru, "REGULATORS", "regulators.kicad_sch", g(20, 170), g(80, 70), "5", REG_PINS),
        (pu, "PROTECTION", "protection.kicad_sch", g(110, 170), g(100, 70), "6", PROT_PINS),
        (iu, "INTERFACE", "interface.kicad_sch", g(220, 170), g(100, 70), "7", IFACE_PINS),
    )
    for su, name, fn, pos, size, page, pin_defs in blocks:
        sch.add_sheet(name, fn, pos, size, project_name=PROJECT_AMP,
                      page_number=page, uuid=su)
        edges = split_edges(len(pin_defs), size[1])
        pins = [(n, sh, edge, along) for (n, sh), (edge, along) in zip(pin_defs, edges)]
        add_sheet_pins(sch, su, pos, size, pins)

    # One PWR_FLAG per shared rail — not on amp_channel, or the three
    # instances short three power outputs together.
    for i, net in enumerate(POWER_NETS):
        _pwr_flag(sch, net, 280, 20 + i * 8)

    return sch, root_uuid, sheet_meta


def main() -> int:
    global _FLAG_N
    _FLAG_N = 0
    setup_cache()
    print("Validating channel_netlist.py …")
    if check_netlist() != 0:
        print("channel_netlist.py has errors; aborting", file=sys.stderr)
        return 1

    AMP.mkdir(parents=True, exist_ok=True)
    PSU.mkdir(parents=True, exist_ok=True)

    print("Generating amp_channel.kicad_sch …")
    ch = build_channel()
    ch_uuid = ch._data["uuid"]
    ch.save(AMP / "amp_channel.kicad_sch")

    print("Generating supporting sheets …")
    build_regulators().save(AMP / "regulators.kicad_sch")
    build_protection().save(AMP / "protection.kicad_sch")
    build_interface().save(AMP / "interface.kicad_sch")
    patch_hier_shapes(AMP / "regulators.kicad_sch", dict(REG_PINS))
    patch_hier_shapes(AMP / "protection.kicad_sch", dict(PROT_PINS))
    patch_hier_shapes(AMP / "interface.kicad_sch", dict(IFACE_PINS))

    print("Generating fs3w-amp.kicad_sch …")
    root, root_uuid, sheet_meta = build_root(ch_uuid)
    root.save(AMP / "fs3w-amp.kicad_sch")

    rewrite_channel_instances(AMP / "amp_channel.kicad_sch", root_uuid, sheet_meta)

    write_lib_tables(AMP)
    write_pro(AMP, PROJECT_AMP, [
        (root_uuid, "Root"),
        (ch_uuid, "AMP_CHANNEL"),
        (uid("regulators"), "REGULATORS"),
        (uid("protection"), "PROTECTION"),
        (uid("interface"), "INTERFACE"),
    ])

    print("Generating fs3w-psu.kicad_sch …")
    psu = build_psu()
    psu.save(PSU / "fs3w-psu.kicad_sch")
    write_lib_tables(PSU)
    write_pro(PSU, PROJECT_PSU, [(psu._data["uuid"], "Root")])

    patch_hier_shapes(AMP / "amp_channel.kicad_sch", HIER_SHAPE)
    print(f"Wrote {AMP} and {PSU}")
    return 0


def patch_hier_shapes(path: Path, shapes: dict[str, str]) -> None:
    """kicad-sch-api always writes (shape input); put the real electrical type back."""
    import re
    text = path.read_text(encoding="utf-8")
    for name, shape in shapes.items():
        text = re.sub(
            rf'\(hierarchical_label "{re.escape(name)}"\s+\(shape \w+\)',
            f'(hierarchical_label "{name}"\n\t\t(shape {shape})',
            text,
        )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
