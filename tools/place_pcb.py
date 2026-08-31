#!/usr/bin/env python3
"""Phase 3: create fs3w-amp.kicad_pcb from the schematic netlist.

    python3 tools/gen_schematic.py
    python3 tools/place_pcb.py
    python3 tools/check_layout.py

Places heatsink devices at the exact docs/05 §5.4 coordinates, remaining
channel parts in regions A–C as identical clusters, and supporting-sheet
parts in E/F. Does not route — that is Phase 4.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("KICAD_CONFIG_HOME", str(Path(__file__).resolve().parents[1] / ".local" / "kicad"))

import pcbnew  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel_netlist import NET_CLASSES  # noqa: E402
from gen_schematic import AMP, PROJECT_AMP, annotate_ref, sch_ref  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PCB = AMP / f"{PROJECT_AMP}.kicad_pcb"
NET = AMP / f"{PROJECT_AMP}.net"
LIB_FP = ROOT / "lib" / "FS3W.pretty"
KICAD_FP = Path("/usr/share/kicad/footprints")

BOARD_W, BOARD_H = 240.0, 160.0
CORNER_R = 3.0
HOLES = ((10, 10), (10, 150), (120, 10), (120, 150), (230, 10), (230, 150))

# docs/05 §5.4 — pad-row centres. CH2/CH3 add +112 mm in x.
HEAT_ROW = (
    ("Q12", 22.95),
    ("Q13", 41.35),
    ("Q10", 56.90),
    ("Q7", 68.50),
    ("Q11", 80.10),
    ("Q14", 95.65),
    ("Q15", 114.05),
)
CH_XOFF = {1: 0.0, 2: 112.0, 3: 112.0}
CH_Y = {1: 8.0, 2: 8.0, 3: 152.0}
CH_ROT = {1: 0.0, 2: 0.0, 3: 180.0}

# Front-end cluster origin (region B) per channel — identical geometry.
FE_ORIGIN = {1: (45.0, 28.0), 2: (70.0, 28.0), 3: (95.0, 28.0)}
# Input cluster origin (region A)
IN_ORIGIN = {1: (8.0, 28.0), 2: (8.0, 52.0), 3: (8.0, 76.0)}
# Output-passive cluster (region C)
OUT_ORIGIN = {1: (125.0, 28.0), 2: (155.0, 28.0), 3: (125.0, 88.0)}

# Local (dx, dy, rot) from cluster origin. Keep Q1/Q3/Q4/Q5/C9 inside 20×20.
FE_LOCAL = {
    "Q1A": (4, 4, 0), "Q3A": (10, 4, 0), "Q4": (4, 12, 0),
    "Q5": (12, 12, 0), "C9": (16, 8, 0),
    "Q2": (4, 20, 0), "R8": (8, 20, 90), "R9": (12, 20, 90),
    "R10": (16, 20, 90), "D1": (20, 16, 0), "R11": (20, 20, 90), "C8": (20, 12, 0),
    "R12": (8, 8, 90), "R13": (12, 8, 90),
    "R14": (4, 16, 90), "R18": (8, 16, 90), "R15": (16, 16, 90),
    "R16": (16, 4, 90), "C10": (20, 4, 0),
    "Q6": (8, 28, 0), "R19": (12, 28, 90), "D2": (16, 28, 0),
    "R20": (20, 28, 90), "C11": (4, 28, 0),
    "R21": (8, 36, 90), "RV2": (14, 36, 0), "R22": (20, 36, 90),
    "C12": (4, 36, 0), "D3": (4, 40, 0),
    "R3": (8, 44, 90), "RV1": (14, 44, 0), "C6": (20, 44, 0),
    "R4": (8, 48, 90), "R6": (12, 48, 90), "C7": (16, 48, 0),
    "R5": (20, 48, 90), "Q16": (4, 48, 0),
    "U2A": (10, 56, 0), "R44": (4, 56, 90), "C15": (16, 56, 0),
    "R45": (4, 60, 90), "R46": (8, 60, 90), "R47": (12, 60, 90),
    "C16": (16, 60, 0), "R49": (20, 60, 90), "R48": (4, 64, 90),
    "C17": (8, 64, 0), "C18": (12, 64, 0),
    "R37": (16, 64, 90), "R38": (20, 64, 90), "C14": (4, 68, 0),
    "R43": (8, 68, 90), "R50": (12, 68, 90),
    "C23": (16, 68, 0), "C24": (20, 68, 0), "C25": (16, 72, 0), "C26": (20, 72, 0),
}

IN_LOCAL = {
    "U1": (18, 10, 0),
    "R1": (6, 6, 90), "R2": (6, 14, 90), "R7": (6, 18, 90),
    "C1": (10, 18, 0), "C2": (14, 6, 0), "C3": (18, 2, 0),
    "C4": (14, 18, 0), "C5": (18, 18, 0),
}

OUT_LOCAL = {
    "R23": (4, 4, 90), "R24": (8, 4, 90), "R25": (12, 4, 90), "R26": (16, 4, 90),
    "R27": (4, 10, 90), "R28": (8, 10, 90), "R29": (12, 10, 90), "R30": (16, 10, 90),
    "R35": (8, 18, 0), "C13": (14, 18, 0), "R36": (20, 18, 0),
    "C19": (8, 28, 0), "C20": (16, 28, 0), "C21": (8, 36, 0), "C22": (16, 36, 0),
}

# L1: CH1 axis 0°, CH2 90°, CH3 90° — pairwise non-parallel where they are close.
L1_POS = {1: (188.0, 40.0, 0.0), 2: (188.0, 70.0, 90.0), 3: (188.0, 120.0, 90.0)}

# Q8/Q9 sit just inboard of the wall (thermal sensing), not in the drill table.
Q89_POS = {
    1: {"Q8": (41.35, 20.0, 0.0), "Q9": (95.65, 20.0, 0.0)},
    2: {"Q8": (153.35, 20.0, 0.0), "Q9": (207.65, 20.0, 0.0)},
    3: {"Q8": (153.35, 140.0, 180.0), "Q9": (207.65, 140.0, 180.0)},
}

# Ballasts immediately inboard of their output devices.
BALLAST = (("R31", "Q12"), ("R32", "Q13"), ("R33", "Q14"), ("R34", "Q15"))

SKIP_FP = re.compile(r"^(#FLG|Q[123]0[13]B$)")

CLASS_GEOM = {
    # name: (track_mm, clearance_mm, via_dia_mm, via_drill_mm)
    "HV_RAIL_MAIN": (12.0, 0.40, 1.6, 0.8),
    "HV_RAIL_CH": (5.0, 0.40, 1.6, 0.8),
    "SPKR_OUT": (5.0, 0.40, 1.6, 0.8),
    "PWR_GND": (12.0, 0.40, 1.6, 0.8),
    "SIG_GND": (0.60, 0.30, 0.8, 0.4),
    "FE_RAIL": (0.80, 0.30, 0.8, 0.4),
    "LV_RAIL": (0.60, 0.30, 0.8, 0.4),
    "AUDIO_IN": (0.35, 0.50, 0.8, 0.4),
    "FEEDBACK": (0.40, 0.50, 0.8, 0.4),
    "BASE_DRIVE": (0.80, 0.30, 0.8, 0.4),
    "HIZ": (0.40, 0.60, 0.8, 0.4),
    "SENSE": (0.35, 0.40, 0.8, 0.4),
    "DEFAULT": (0.35, 0.30, 0.8, 0.4),
}


def mm(x: float, y: float):
    return pcbnew.VECTOR2I_MM(float(x), float(y))


def parse_netlist(path: Path) -> tuple[dict[str, dict], dict[str, list[tuple[str, str]]]]:
    text = path.read_text(encoding="utf-8")
    comps: dict[str, dict] = {}
    for m in re.finditer(
        r'\(comp\s+\(ref\s+"([^"]+)"\)\s+\(value\s+"([^"]*)"\)\s+\(footprint\s+"([^"]*)"\)',
        text,
    ):
        comps[m.group(1)] = {"value": m.group(2), "footprint": m.group(3)}
    # looser: footprint may be missing
    if not comps:
        for m in re.finditer(r'\(comp\s+\(ref\s+"([^"]+)"\)(.*?)(?=\n\s+\(comp\s+|\n\s+\)\s*\n\s+\(libpart|\n\s+\(nets)', text, re.S):
            ref, body = m.group(1), m.group(2)
            val = re.search(r'\(value\s+"([^"]*)"\)', body)
            fp = re.search(r'\(footprint\s+"([^"]*)"\)', body)
            comps[ref] = {"value": val.group(1) if val else "", "footprint": fp.group(1) if fp else ""}
    nets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for m in re.finditer(
        r'\(net\s+\(code\s+"[^"]+"\)\s+\(name\s+"([^"]+)"\)(.*?)(?=\n\s+\(net\s+\(code|\n\s+\)\s*\n\))',
        text, re.S,
    ):
        name = m.group(1).split("/")[-1]
        for ref, pin in re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)', m.group(2)):
            nets[name].append((ref, pin))
    return comps, dict(nets)


def load_footprint(fp_id: str):
    if not fp_id or ":" not in fp_id:
        return None
    lib, name = fp_id.split(":", 1)
    pretty = str(LIB_FP) if lib == "FS3W" else str(KICAD_FP / f"{lib}.pretty")
    try:
        return pcbnew.FootprintLoad(pretty, name)
    except Exception:
        return None


def add_net(board, name: str):
    existing = board.FindNet(name)
    if existing:
        return existing
    item = pcbnew.NETINFO_ITEM(board, name)
    board.Add(item)
    return board.FindNet(name)


def set_stackup(board) -> None:
    board.SetCopperLayerCount(4)
    board.SetLayerName(pcbnew.F_Cu, "L1_Power")
    board.SetLayerName(pcbnew.In1_Cu, "L2_GND")
    board.SetLayerName(pcbnew.In2_Cu, "L3_Rails")
    board.SetLayerName(pcbnew.B_Cu, "L4_Return")
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = pcbnew.FromMM(0.15)
    ds.m_MinClearance = pcbnew.FromMM(0.15)
    ds.m_ViasMinSize = pcbnew.FromMM(0.6)
    ds.m_ViasMinDrill = pcbnew.FromMM(0.3)


def set_netclasses(board) -> None:
    ns = board.GetDesignSettings().m_NetSettings
    default = ns.GetDefaultNetclass()
    tw, cl, vd, vdr = CLASS_GEOM["DEFAULT"]
    default.SetTrackWidth(pcbnew.FromMM(tw))
    default.SetClearance(pcbnew.FromMM(cl))
    default.SetViaDiameter(pcbnew.FromMM(vd))
    default.SetViaDrill(pcbnew.FromMM(vdr))
    for name, (tw, cl, vd, vdr) in CLASS_GEOM.items():
        if name == "DEFAULT":
            continue
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(pcbnew.FromMM(tw))
        nc.SetClearance(pcbnew.FromMM(cl))
        nc.SetViaDiameter(pcbnew.FromMM(vd))
        nc.SetViaDrill(pcbnew.FromMM(vdr))
        nc.SetDescription(f"docs/05 §5.2 {name}")
        ns.SetNetclass(name, nc)
        for net in NET_CLASSES.get(name, []):
            ns.SetNetclassPatternAssignment(net, name)
            ns.SetNetclassPatternAssignment(f"*{net}*", name)
    board.SynchronizeNetsAndNetClasses(True)


def outline_and_holes(board) -> None:
    w, h, r = BOARD_W, BOARD_H, CORNER_R

    def line(x1, y1, x2, y2):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(mm(x1, y1))
        s.SetEnd(mm(x2, y2))
        s.SetWidth(pcbnew.FromMM(0.1))
        board.Add(s)

    def arc(cx, cy, start, end):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        # KiCad 10: SetCenter + SetStart + SetArcAngleAndEnd, or SetArcGeometry
        if hasattr(s, "SetArcGeometry"):
            s.SetArcGeometry(mm(*start), mm(cx, cy), mm(*end))
        else:
            s.SetStart(mm(*start))
            s.SetEnd(mm(*end))
            s.SetCenter(mm(cx, cy))
        board.Add(s)

    line(r, 0, w - r, 0)
    line(w, r, w, h - r)
    line(w - r, h, r, h)
    line(0, h - r, 0, r)
    arc(w - r, r, (w - r, 0), (w, r))
    arc(w - r, h - r, (w, h - r), (w - r, h))
    arc(r, h - r, (r, h), (0, h - r))
    arc(r, r, (0, r), (r, 0))

    for i, (x, y) in enumerate(HOLES, 1):
        fp = load_footprint("MountingHole:MountingHole_3.2mm_M3")
        if fp is None:
            # fallback: NPTH pad on a dummy footprint
            continue
        fp.SetReference(f"H{i}")
        fp.SetValue("M3")
        fp.SetPosition(mm(x, y))
        fp.SetLocked(True)
        board.Add(fp)


def place_fp(board, ref: str, meta: dict, x: float, y: float, rot: float,
             nets: dict[str, list[tuple[str, str]]]) -> bool:
    fp = load_footprint(meta.get("footprint", ""))
    if fp is None:
        return False
    fp.SetReference(ref)
    fp.SetValue(meta.get("value") or ref)
    fp.SetPosition(mm(x, y))
    fp.SetOrientationDegrees(rot)
    # Assign pads from netlist
    pad_nets = {pin: name for name, nodes in nets.items() for r, pin in nodes if r == ref}
    for pad in fp.Pads():
        pname = str(pad.GetNumber())
        if pname in pad_nets:
            pad.SetNet(add_net(board, pad_nets[pname]))
    board.Add(fp)
    return True


def channel_xy(base_ref: str, channel: int) -> tuple[float, float, float] | None:
    if base_ref == "U2":
        base_ref = "U2A"
    if base_ref in {p[0] for p in HEAT_ROW}:
        x0 = dict(HEAT_ROW)[base_ref]
        return (x0 + CH_XOFF[channel], CH_Y[channel], CH_ROT[channel])
    if base_ref in ("Q8", "Q9"):
        return Q89_POS[channel][base_ref]
    if base_ref == "L1":
        return L1_POS[channel]
    if base_ref in dict(BALLAST):
        mate = dict(BALLAST)[base_ref]
        x0 = dict(HEAT_ROW)[mate] + CH_XOFF[channel]
        y = 20.0 if channel < 3 else 140.0
        return (x0, y, 90.0 if channel < 3 else 270.0)
    if base_ref in FE_LOCAL:
        ox, oy = FE_ORIGIN[channel]
        dx, dy, rot = FE_LOCAL[base_ref]
        return (ox + dx, oy + dy, rot)
    if base_ref in IN_LOCAL:
        ox, oy = IN_ORIGIN[channel]
        dx, dy, rot = IN_LOCAL[base_ref]
        return (ox + dx, oy + dy, rot)
    if base_ref in OUT_LOCAL:
        ox, oy = OUT_ORIGIN[channel]
        dx, dy, rot = OUT_LOCAL[base_ref]
        return (ox + dx, oy + dy, rot)
    return None


def deannotate(ref: str) -> tuple[str, int] | None:
    """R101 → (R1, 1), Q101A → (Q1A, 1), U102 → (U2, 1)."""
    m = re.match(r"^([A-Z]+)([123])(\d{2})([A-Z]*)$", ref)
    if not m:
        return None
    prefix, ch, num, suf = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    return f"{prefix}{int(num)}{suf}", ch


def place_supporting(board, comps: dict, nets: dict, placed: set[str]) -> None:
    """Region E / F leftovers: pack on a grid."""
    e_x, e_y = 8.0, 118.0
    f_x, f_y = 208.0, 20.0
    e_col, f_col = 0, 0
    for ref, meta in sorted(comps.items()):
        if ref in placed or SKIP_FP.match(ref):
            continue
        if deannotate(ref):
            continue
        if not meta.get("footprint"):
            print(f"  skip {ref}: no footprint")
            continue
        if ref.startswith("J40") and ref[-1] in "4567":
            x, y = f_x + (f_col % 2) * 14, f_y + (f_col // 2) * 16
            f_col += 1
        elif ref.startswith("J"):
            x, y = 6.0 + e_col * 0, 28.0 + hash(ref) % 3 * 8  # overwritten below
            x, y = 6.0, 30.0 + (ord(ref[-1]) - ord("1")) * 12
        else:
            x = e_x + (e_col % 10) * 8
            y = e_y + (e_col // 10) * 8
            e_col += 1
        if place_fp(board, ref, meta, x, y, 0, nets):
            placed.add(ref)
        else:
            print(f"  skip {ref}: cannot load {meta.get('footprint')}")


def export_netlist() -> None:
    sch = AMP / f"{PROJECT_AMP}.kicad_sch"
    r = subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--output", str(NET), str(sch)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stderr or r.stdout)
        raise SystemExit("netlist export failed")


def write_drill_table(path: Path) -> None:
    lines = ["channel,ref,x_mm,y_mm,rotation_deg"]
    for ch in (1, 2, 3):
        for base, x0 in HEAT_ROW:
            ref = annotate_ref(base, ch)
            lines.append(f"{ch},{ref},{x0 + CH_XOFF[ch]:.2f},{CH_Y[ch]:.1f},{CH_ROT[ch]:.0f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    AMP.mkdir(parents=True, exist_ok=True)
    print("export netlist")
    export_netlist()
    comps, nets = parse_netlist(NET)
    print(f"  {len(comps)} components, {len(nets)} nets")

    board = pcbnew.CreateEmptyBoard()
    set_stackup(board)
    outline_and_holes(board)

    placed: set[str] = set()
    missing = []
    for ref, meta in sorted(comps.items()):
        if SKIP_FP.match(ref):
            continue
        dec = deannotate(ref)
        if not dec:
            continue
        base, ch = dec
        # Dual-package half already skipped by SKIP_FP for QxB; U2 units share U102
        pos = channel_xy(base, ch)
        if pos is None:
            continue
        x, y, rot = pos
        if place_fp(board, ref, meta, x, y, rot, nets):
            placed.add(ref)
        else:
            missing.append(f"{ref} ({meta.get('footprint')})")
    place_supporting(board, comps, nets, placed)
    set_netclasses(board)

    for h in board.GetFootprints():
        if h.GetReference().startswith("H"):
            placed.add(h.GetReference())

    pcbnew.Refresh()
    pcbnew.SaveBoard(str(PCB), board)
    write_drill_table(ROOT / "docs" / "heatsink-drill.csv")
    print(f"placed {len(placed)} footprints → {PCB}")
    if missing:
        print(f"{len(missing)} footprints failed to load:")
        for m in missing[:20]:
            print(f"  {m}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
