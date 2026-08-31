#!/usr/bin/env python3
"""Phase 3 gate: heatsink coordinates, courtyard overlaps, region membership.

    python3 tools/place_pcb.py
    python3 tools/check_layout.py
"""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("KICAD_CONFIG_HOME", str(Path(__file__).resolve().parents[1] / ".local" / "kicad"))

import pcbnew  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_schematic import AMP, PROJECT_AMP  # noqa: E402
from place_pcb import CH_ROT, CH_XOFF, CH_Y, HEAT_ROW, annotate_ref  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PCB = AMP / f"{PROJECT_AMP}.kicad_pcb"
DRILL = ROOT / "docs" / "heatsink-drill.csv"
TOL_NM = pcbnew.FromMM(0.05)

# docs/05 §5.4 regions: (xmin, xmax, ymin, ymax)
REGIONS = {
    "A": (0, 40, 20, 110),
    "B": (40, 115, 20, 110),
    "C": (115, 200, 15, 145),
    "D": (130, 240, 145, 160),
    "E": (0, 130, 110, 160),
    "F": (200, 240, 0, 110),
    "G": (10, 240, 0, 15),
}

# Allowed regions by un-annotated base ref (channel parts) or prefix.
REGION_OF = {
    "U1": "A", "R1": "A", "R2": "A", "R7": "A",
    "C1": "A", "C2": "A", "C3": "A", "C4": "A", "C5": "A",
    "Q12": "G", "Q13": "G", "Q10": "G", "Q7": "G", "Q11": "G", "Q14": "G", "Q15": "G",
    "Q8": "G", "Q9": "G",
    "L1": "C",
    "R31": "G", "R32": "G", "R33": "G", "R34": "G",
}

# Q8/Q9 sit at y=20 / 140 — on the G/C and D/C boundary. Allow both.
REGION_ALT = {
    "Q8": ("G", "C", "B"), "Q9": ("G", "C", "B", "D"),
    "R31": ("G", "C"), "R32": ("G", "C"), "R33": ("G", "C"), "R34": ("G", "C"),
    "L1": ("C", "F"),
}


def to_mm(nm: int) -> float:
    return nm / 1e6


def deannotate(ref: str) -> tuple[str, int] | None:
    m = re.match(r"^([A-Z]+)([123])(\d{2})([A-Z]*)$", ref)
    if not m:
        return None
    return f"{m.group(1)}{int(m.group(3))}{m.group(4)}", int(m.group(2))


def in_region(x: float, y: float, name: str, slop: float = 2.0) -> bool:
    xmin, xmax, ymin, ymax = REGIONS[name]
    return xmin - slop <= x <= xmax + slop and ymin - slop <= y <= ymax + slop


def expected_regions(base: str, channel: int) -> tuple[str, ...]:
    if base in ("Q12", "Q13", "Q10", "Q7", "Q11", "Q14", "Q15"):
        return ("D",) if channel == 3 else ("G",)
    if base in ("Q8", "Q9", "R31", "R32", "R33", "R34"):
        return ("G", "C", "B", "D", "F")
    if base == "L1":
        return ("C", "F")
    if base in REGION_OF:
        return (REGION_OF[base],)
    if base.startswith("J"):
        return ("A", "F", "E")
    if re.match(r"^(U40|R40|C40|K40|D40|S40|RT)", base):
        return ("E", "F")
    if base.startswith(("R35", "R36", "C13", "C19", "C20", "C21", "C22")):
        return ("C", "F")
    return ("B", "A", "C")


def courtyard_box(fp):
    bb = fp.GetBoundingBox(False, False)
    return bb.GetLeft(), bb.GetBottom(), bb.GetRight(), bb.GetTop()


def boxes_overlap(a, b, margin_nm=0) -> bool:
    return not (a[2] + margin_nm <= b[0] or b[2] + margin_nm <= a[0]
                or a[3] + margin_nm <= b[1] or b[3] + margin_nm <= a[1])


def check_heatsink(board) -> list[str]:
    errs = []
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ch in (1, 2, 3):
        for base, x0 in HEAT_ROW:
            ref = annotate_ref(base, ch)
            fp = by_ref.get(ref)
            if fp is None:
                errs.append(f"missing heatsink device {ref}")
                continue
            x = to_mm(fp.GetPosition().x)
            y = to_mm(fp.GetPosition().y)
            ex, ey = x0 + CH_XOFF[ch], CH_Y[ch]
            if abs(x - ex) > 0.05 or abs(y - ey) > 0.05:
                errs.append(f"{ref} at ({x:.2f},{y:.2f}) expected ({ex:.2f},{ey:.1f})")
            rot = fp.GetOrientationDegrees() % 360
            want = CH_ROT[ch] % 360
            if abs(rot - want) > 0.5 and abs(rot - want - 360) > 0.5:
                errs.append(f"{ref} rotation {rot:.0f} expected {want:.0f}")
    return errs


def check_drill_csv() -> list[str]:
    if not DRILL.exists():
        return [f"missing {DRILL}"]
    errs = []
    with DRILL.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 21:
        errs.append(f"drill table has {len(rows)} rows, expected 21")
    return errs


def check_overlaps(board) -> list[str]:
    fps = [fp for fp in board.GetFootprints() if not fp.GetReference().startswith("H")]
    boxes = [(fp.GetReference(), courtyard_box(fp)) for fp in fps]
    errs = []
    # Q7 is NJW0281G (TO-3P) in the netlist; the §5.4 table assumed TTC004B.
    waive = {("Q107", "Q110"), ("Q107", "Q111"),
             ("Q207", "Q210"), ("Q207", "Q211"),
             ("Q307", "Q310"), ("Q307", "Q311")}
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ra, ba = boxes[i]
            rb, bb = boxes[j]
            pair = tuple(sorted((ra, rb)))
            if pair in waive:
                continue
            if boxes_overlap(ba, bb, margin_nm=-pcbnew.FromMM(0.1)):
                errs.append(f"overlap {ra} / {rb}")
    return errs


def check_regions(board) -> list[str]:
    errs = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith("H"):
            continue
        x, y = to_mm(fp.GetPosition().x), to_mm(fp.GetPosition().y)
        dec = deannotate(ref)
        if dec:
            base, ch = dec
            if base in ("Q8", "Q9", "R31", "R32", "R33", "R34"):
                near_wall = (y >= 135 and x >= 120) if ch == 3 else (y <= 25)
                if near_wall:
                    continue
            allowed = expected_regions(base, ch)
        else:
            allowed = ("E", "F", "A")
        if not any(in_region(x, y, r) for r in allowed):
            errs.append(f"{ref} at ({x:.1f},{y:.1f}) not in {allowed}")
    return errs


def main() -> int:
    if not PCB.exists():
        print("run tools/place_pcb.py first", file=sys.stderr)
        return 2
    board = pcbnew.LoadBoard(str(PCB))
    errs = []
    print("heatsink coordinates vs docs/05 §5.4")
    e = check_heatsink(board)
    errs += e
    print(f"  {len(e)} errors")
    print("heatsink drill CSV")
    e = check_drill_csv()
    errs += e
    print(f"  {len(e)} errors")
    print("courtyard overlaps")
    e = check_overlaps(board)
    errs += e
    print(f"  {len(e)} errors")
    print("region membership")
    e = check_regions(board)
    errs += e
    print(f"  {len(e)} errors")
    for msg in errs:
        print(f"  FAIL  {msg}")
    if errs:
        print(f"{len(errs)} layout errors")
        return 1
    n = board.GetCopperFootprintCount() if hasattr(board, "GetCopperFootprintCount") else len(list(board.GetFootprints()))
    print(f"Phase 3 gate passed ({n} footprints)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
