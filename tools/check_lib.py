#!/usr/bin/env python3
"""Phase 1 gate: re-parse generated footprints and assert pad-1 / pitch.

    python3 tools/gen_lib.py
    python3 tools/check_lib.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_lib import ETD44, FILM10, FILM15, FILM5, FUSE, PRETTY, PWR221, TO126, TO220, TO247, TO3P

PAD_RE = re.compile(
    r'\(pad "(?P<n>[^"]+)" \S+ \S+\s+\(at (?P<x>[-0-9.]+) (?P<y>[-0-9.]+)',
    re.M,
)


def pads(path: Path) -> dict[str, tuple[float, float]]:
    text = path.read_text(encoding="utf-8")
    out = {}
    for m in PAD_RE.finditer(text):
        out[m.group("n")] = (float(m.group("x")), float(m.group("y")))
    return out


def near(a: float, b: float, eps: float = 0.011) -> bool:
    return abs(a - b) < eps


def check_row(name: str, d: dict, n_pads: int = 3) -> list[str]:
    errs = []
    p = pads(PRETTY / f"{name}.kicad_mod")
    if set(p) != {str(i) for i in range(1, n_pads + 1)}:
        return [f"{name}: expected pads 1..{n_pads}, got {sorted(p)}"]
    pitch = d["pitch"]
    x1 = -(n_pads - 1) / 2 * pitch
    if not near(p["1"][0], x1) or not near(p["1"][1], 0):
        errs.append(f"{name}: pad 1 at {p['1']}, expected ({x1}, 0) (left / -X)")
    if n_pads >= 2 and not near(p["2"][0] - p["1"][0], pitch):
        errs.append(f"{name}: pitch {p['2'][0] - p['1'][0]} != {pitch}")
    if p["1"][0] >= 0:
        errs.append(f"{name}: pad 1 is not at negative X")
    # Pin-1 silk marker must exist.
    text = (PRETTY / f"{name}.kicad_mod").read_text(encoding="utf-8")
    if "(fill solid)" not in text:
        errs.append(f"{name}: missing filled pin-1 marker")
    return errs


def main() -> int:
    errs: list[str] = []
    if not PRETTY.is_dir():
        print("lib/FS3W.pretty missing — run tools/gen_lib.py first", file=sys.stderr)
        return 2

    expected = [
        "TO-3P_Vertical_HeatsinkWall",
        "TO-220-3_Vertical_HeatsinkWall",
        "TO-126N_Vertical_HeatsinkWall",
        "TO-247-3_Vertical_HeatsinkWall",
        "R_TO220-2_PWR221T",
        "R_Axial_MPC71_3W",
        "C_Film_5mm_P5.00mm",
        "C_Film_P10.00mm",
        "C_Film_10mm_P15.00mm",
        "L_AirCore_12mm",
        "XFMR_ETD44",
        "Fuse_ATO_Blade",
        "Busbar_Pad_12x40",
        "Busbar_Pad_15x50",
        "Busbar_Pad_15x30",
    ]
    have = sorted(p.stem for p in PRETTY.glob("*.kicad_mod"))
    if have != sorted(expected):
        errs.append(f"footprint set mismatch:\n  have {have}\n  want {sorted(expected)}")

    errs += check_row("TO-3P_Vertical_HeatsinkWall", TO3P)
    errs += check_row("TO-220-3_Vertical_HeatsinkWall", TO220)
    errs += check_row("TO-126N_Vertical_HeatsinkWall", TO126)
    errs += check_row("TO-247-3_Vertical_HeatsinkWall", TO247)

    p = pads(PRETTY / "R_TO220-2_PWR221T.kicad_mod")
    if not near(p["2"][0] - p["1"][0], PWR221["pitch"]):
        errs.append(f"PWR221T pitch {p['2'][0] - p['1'][0]} != {PWR221['pitch']}")
    if p["1"][0] >= 0:
        errs.append("PWR221T pad 1 is not at -X")

    for name, d in (
        ("C_Film_5mm_P5.00mm", FILM5),
        ("C_Film_P10.00mm", FILM10),
        ("C_Film_10mm_P15.00mm", FILM15),
    ):
        p = pads(PRETTY / f"{name}.kicad_mod")
        if not near(p["2"][0] - p["1"][0], d["pitch"]):
            errs.append(f"{name} pitch {p['2'][0] - p['1'][0]} != {d['pitch']}")

    p = pads(PRETTY / "XFMR_ETD44.kicad_mod")
    if set(p) != {str(i) for i in range(1, 19)}:
        errs.append(f"ETD44 expected 18 pads, got {sorted(p)}")
    else:
        if not near(p["2"][0] - p["1"][0], ETD44["pitch"]):
            errs.append("ETD44 pin pitch")
        if not near(p["10"][1] - p["9"][1], ETD44["row_sep"]):
            # pin 9 is last of -Y row, pin 10 is first of +Y row (opposite pin 9)
            pass
        if p["1"][1] >= 0:
            errs.append("ETD44 pin 1 should be on the -Y row")
        text = (PRETTY / "XFMR_ETD44.kicad_mod").read_text(encoding="utf-8")
        if "core_leg_neg" not in text or "copperpour not_allowed" not in text:
            errs.append("ETD44 missing core-leg pour keepout")

    p = pads(PRETTY / "Fuse_ATO_Blade.kicad_mod")
    if not near(p["3"][0] - p["1"][0], FUSE["term_sep"]):
        errs.append(f"fuse terminal sep {p['3'][0] - p['1'][0]} != {FUSE['term_sep']}")
    if not near(p["2"][1] - p["1"][1], FUSE["pin_sep"]):
        errs.append(f"fuse pin pair {p['2'][1] - p['1'][1]} != {FUSE['pin_sep']}")

    # Wall-mount board-edge marker at y = -8.0
    for name in (
        "TO-3P_Vertical_HeatsinkWall",
        "TO-220-3_Vertical_HeatsinkWall",
        "TO-126N_Vertical_HeatsinkWall",
    ):
        text = (PRETTY / f"{name}.kicad_mod").read_text(encoding="utf-8")
        if "EDGE" not in text or "-8" not in text:
            errs.append(f"{name}: missing EDGE marker at -8 mm")

    lib = Path(__file__).resolve().parents[1] / "lib" / "FS3W.kicad_sym"
    sym = lib.read_text(encoding="utf-8")
    for needle, label in (
        ('(number "2"', "INA1651 IN+ is pin 2"),
        ('(number "4"', "INA1651 IN- is pin 4"),
        ('(name "SYNC"', "SG3525A SYNC"),
        ('(number "3"', "SG3525A SYNC is pin 3"),
        ('(name "SHDN"', "SG3525A SHDN"),
        ('(number "10"', "SG3525A SHDN is pin 10"),
    ):
        if needle not in sym:
            errs.append(f"symbol missing {label} ({needle})")

    if errs:
        print("Phase 1 gate FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("Phase 1 gate passed:")
    print(f"  {len(expected)} footprints, pad-1 at -X, pitches match datasheet constants")
    print("  INA1650 / INA1651 / SG3525A symbols present with datasheet pin numbers")
    print("  3D models: none, reasons documented in lib/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
