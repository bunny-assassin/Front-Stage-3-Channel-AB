#!/usr/bin/env python3
"""Generate lib/FS3W.pretty and lib/FS3W.kicad_sym.

Dimensions are named constants with a datasheet citation. tools/check_lib.py
re-reads the emitted files and asserts pad-1 position and pitch against these
same constants — that is the Phase 1 gate.

    python3 tools/gen_lib.py
    python3 tools/check_lib.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRETTY = ROOT / "lib" / "FS3W.pretty"
SYM = ROOT / "lib" / "FS3W.kicad_sym"
README = ROOT / "lib" / "README.md"

# KiCad 8/9 footprint format. 9 will load this; do not bump blindly.
KICAD_FP_VER = "20240108"
KICAD_SYM_VER = "20231120"

# ---------------------------------------------------------------------------
# Datasheet-backed dimensions (mm). Citations in lib/README.md.
# ---------------------------------------------------------------------------

# onsemi CASE 340AB (NJW0281G / NJW0302G). Pitch G = 5.45 BSC.
# Body B = 15.60 nom (docs/05 uses 15.9 mm max). Pad row 8.0 mm from board
# edge is locked by docs/05 §5.4 (heatsink drill table).
TO3P = dict(
    pitch=5.45, body_w=15.80, body_h=19.90, lead_d=1.10, drill=1.40,
    pad_w=2.80, pad_h=2.40, edge=8.0, hole_d=3.50,
)

# JEDEC TO-220AB (MJE15032G / IRFB4110). Pitch 2.54. Body width 10.2 mm
# matches docs/05 package-width table.
TO220 = dict(
    pitch=2.54, body_w=10.20, body_h=15.70, lead_d=0.80, drill=1.10,
    pad_w=2.20, pad_h=1.80, edge=8.0, hole_d=3.70,
)

# Toshiba 2-8U1A / TO-126N (TTC004B / TTA004B). Body 8.0 × 11.0 × 3.25.
# Lead pitch 2.29 mm (TO-126 family).
TO126 = dict(
    pitch=2.29, body_w=8.00, body_h=11.00, lead_d=0.70, drill=0.95,
    pad_w=1.80, pad_h=1.60, edge=8.0, hole_d=3.20,
)

# ST TO-247 (STPS40H100CW). Pitch typically 5.44 mm. Not in the original
# docs/07 list; required for the PSU rectifiers on a heatsink wall.
TO247 = dict(
    pitch=5.44, body_w=15.90, body_h=20.80, lead_d=1.20, drill=1.50,
    pad_w=3.00, pad_h=2.50, edge=8.0, hole_d=3.60,
)

# Bourns PWR221T-20: TO-220-2, 5.08 mm pitch, standing on the board
# (ballasts sit at the device leads, not on the chassis wall).
PWR221 = dict(pitch=5.08, body_w=10.41, body_h=16.26, drill=1.10, pad=2.20)

# Ferroxcube CPH-ETD44-1S-18P (Farnell drawing). 9 pins × 2 rows, 5.08 pitch,
# 40.64 mm pin span, 35.56 mm row spacing.
ETD44 = dict(
    pitch=5.08, n_per_row=9, row_sep=35.56, pin_span=40.64,
    body_x=49.6, body_y=52.2, core_len=44.0, core_thk=16.0, drill=1.30, pad=2.40,
)

# Littelfuse 178.6165.0001 hole pattern: 20 mm between terminals, 5.8 mm
# between the two pins of one terminal, 1.5 mm holes.
FUSE = dict(term_sep=20.0, pin_sep=5.80, drill=1.50, pad=2.80, body_l=21.6, body_w=17.5)

# WIMA MKS2 / MKS4 typical bodies. Pitch is the spec; body is courtyard.
FILM5 = dict(pitch=5.00, body_l=7.2, body_w=4.5, drill=0.80, pad=1.60)
FILM10 = dict(pitch=10.00, body_l=13.0, body_w=6.0, drill=0.80, pad=1.80)
FILM15 = dict(pitch=15.00, body_l=18.0, body_w=8.5, drill=0.90, pad=2.00)

# Air-core 12 mm ID, ~1.0 mm wire, ~12 turns. Leads 12 mm apart.
AIRCORE = dict(id=12.0, od=18.0, lead_sep=12.0, drill=1.20, pad=2.20)


def uid(*parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def mm(n: float) -> str:
    s = f"{n:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"


# ---------------------------------------------------------------------------
# Footprint S-expression helpers
# ---------------------------------------------------------------------------

class FP:
    def __init__(self, name: str, descr: str, tags: str):
        self.name = name
        self.descr = descr
        self.tags = tags
        self.lines: list[str] = []

    def _u(self, extra: str) -> str:
        return uid(self.name, extra)

    def add(self, s: str) -> None:
        self.lines.append(s)

    def prop(self, key: str, val: str, x: float, y: float, layer: str, hide: bool = False) -> None:
        hide_s = "\n    (hide yes)" if hide else ""
        self.add(f'''  (property "{key}" "{val}"
    (at {mm(x)} {mm(y)} 0)
    (layer "{layer}"){hide_s}
    (uuid "{self._u("prop-"+key)}")
    (effects
      (font
        (size 1 1)
        (thickness 0.15)
      )
    )
  )''')

    def line(self, x1, y1, x2, y2, layer, w=0.12) -> None:
        self.add(f'''  (fp_line
    (start {mm(x1)} {mm(y1)})
    (end {mm(x2)} {mm(y2)})
    (stroke (width {mm(w)}) (type solid))
    (layer "{layer}")
    (uuid "{self._u(f"ln-{x1}-{y1}-{x2}-{y2}-{layer}")}")
  )''')

    def rect(self, x1, y1, x2, y2, layer, w=0.05, fill="none") -> None:
        self.add(f'''  (fp_rect
    (start {mm(x1)} {mm(y1)})
    (end {mm(x2)} {mm(y2)})
    (stroke (width {mm(w)}) (type solid))
    (fill {fill})
    (layer "{layer}")
    (uuid "{self._u(f"rc-{x1}-{y1}-{x2}-{y2}-{layer}")}")
  )''')

    def circle(self, x, y, r, layer, w=0.12, fill="none") -> None:
        self.add(f'''  (fp_circle
    (center {mm(x)} {mm(y)})
    (end {mm(x + r)} {mm(y)})
    (stroke (width {mm(w)}) (type solid))
    (fill {fill})
    (layer "{layer}")
    (uuid "{self._u(f"cir-{x}-{y}-{r}-{layer}")}")
  )''')

    def text(self, txt, x, y, layer, size=0.8) -> None:
        self.add(f'''  (fp_text user "{txt}"
    (at {mm(x)} {mm(y)} 0)
    (layer "{layer}")
    (uuid "{self._u("txt-"+txt)}")
    (effects
      (font
        (size {mm(size)} {mm(size)})
        (thickness {mm(size * 0.15)})
      )
    )
  )''')

    def pad(self, num, x, y, sx, sy, drill, shape="roundrect") -> None:
        extra = " (roundrect_rratio 0.15)" if shape == "roundrect" else ""
        # Pad 1 is rectangular so it is visually distinct on the copper.
        if str(num) == "1":
            shape = "rect"
            extra = ""
        self.add(f'''  (pad "{num}" thru_hole {shape}
    (at {mm(x)} {mm(y)})
    (size {mm(sx)} {mm(sy)})
    (drill {mm(drill)})
    (layers "*.Cu" "*.Mask")
    (remove_unused_layers no){extra}
    (uuid "{self._u("pad-"+str(num))}")
  )''')

    def smd_pad(self, num, x, y, sx, sy, layers='"F.Cu" "F.Mask"') -> None:
        self.add(f'''  (pad "{num}" smd rect
    (at {mm(x)} {mm(y)})
    (size {mm(sx)} {mm(sy)})
    (layers {layers})
    (uuid "{self._u("smd-"+str(num))}")
  )''')

    def keepout(self, x1, y1, x2, y2, name: str) -> None:
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        pt_s = " ".join(f"(xy {mm(x)} {mm(y)})" for x, y in pts)
        self.add(f'''  (zone
    (net 0)
    (net_name "")
    (layers "*.Cu")
    (uuid "{self._u("z-"+name)}")
    (name "{name}")
    (hatch edge 0.5)
    (keepout
      (tracks not_allowed)
      (vias not_allowed)
      (pads allowed)
      (copperpour not_allowed)
      (footprints allowed)
    )
    (polygon
      (pts {pt_s})
    )
  )''')

    def emit(self) -> str:
        body = "\n".join(self.lines)
        return f'''(footprint "{self.name}"
  (version {KICAD_FP_VER})
  (generator "fs3w_gen_lib")
  (layer "F.Cu")
  (descr "{self.descr}")
  (tags "{self.tags}")
  (attr through_hole)
{body}
)
'''


def wall_mount(name: str, d: dict, descr: str, n_pads: int = 3) -> FP:
    """Pads on a row at y=0. Wall / board edge at y=-edge. Pad 1 at -X.

    Looking from the board interior toward the heatsink wall, pad 1 is on
    the left. That matches the datasheet front-view pin 1 (leftmost lead
    when the printed face is toward you and the tab is against the wall).
    """
    fp = FP(name, descr, "TO heatsink-wall FS3W")
    pitch, n = d["pitch"], n_pads
    xs = [-(n - 1) / 2 * pitch + i * pitch for i in range(n)]
    fp.prop("Reference", "REF**", 0, d["pad_h"] / 2 + 1.8, "F.SilkS")
    fp.prop("Value", name, 0, -d["edge"] / 2, "F.Fab")
    fp.prop("Datasheet", "", 0, 0, "F.Fab", hide=True)
    fp.prop("Description", descr, 0, 0, "F.Fab", hide=True)
    for i, x in enumerate(xs, start=1):
        fp.pad(i, x, 0, d["pad_w"], d["pad_h"], d["drill"])
    # Body silk toward the wall (negative Y).
    bw, bh, edge = d["body_w"], d["body_h"], d["edge"]
    fp.rect(-bw / 2, -1.0, bw / 2, -edge, "F.SilkS", 0.12)
    fp.rect(-bw / 2, -1.0, bw / 2, -edge, "F.Fab", 0.10)
    # Board-edge marker.
    fp.line(-bw / 2 - 1, -edge, bw / 2 + 1, -edge, "Dwgs.User", 0.15)
    fp.text("EDGE", bw / 2 + 2.5, -edge, "Dwgs.User", 0.7)
    # Pin-1 marker (left, interior side of pad row).
    fp.circle(xs[0], d["pad_h"] / 2 + 0.9, 0.35, "F.SilkS", 0.12, "solid")
    fp.circle(xs[0], d["pad_h"] / 2 + 0.9, 0.35, "F.Fab", 0.10, "solid")
    # M3 bolt projection on the wall, off the board. Drawing layer only.
    bolt_y = -edge - 6.0
    fp.circle(0, bolt_y, d["hole_d"] / 2, "Dwgs.User", 0.15)
    fp.circle(0, bolt_y, 1.5, "Dwgs.User", 0.10)
    fp.text("M3", 3.2, bolt_y, "Dwgs.User", 0.7)
    # Courtyard: pads plus the on-board lead-form strip to the edge.
    cx = bw / 2 + 1.0
    fp.rect(-cx, -edge - 0.25, cx, d["pad_h"] / 2 + 1.5, "F.CrtYd", 0.05)
    # Keepout: no pour in the 8 mm strip between pads and the wall.
    fp.keepout(-cx, -edge, cx, -d["pad_h"] / 2, "lead_form_strip")
    return fp


def pwr221() -> FP:
    d = PWR221
    fp = FP(
        "R_TO220-2_PWR221T",
        "Bourns PWR221T-20 / Caddock MP930 TO-220-2 standing. Pitch 5.08 mm. "
        "Not wall-mounted: ballasts sit at the output device leads. "
        "No 3D: stock TO-220 models include a tab pin this package does not have.",
        "TO-220 resistor FS3W",
    )
    x = d["pitch"] / 2
    fp.prop("Reference", "REF**", 0, 10.5, "F.SilkS")
    fp.prop("Value", "R_TO220-2_PWR221T", 0, -2.2, "F.Fab")
    fp.pad(1, -x, 0, d["pad"], d["pad"] + 0.4, d["drill"])
    fp.pad(2, x, 0, d["pad"], d["pad"] + 0.4, d["drill"])
    bw, bh = d["body_w"], d["body_h"]
    fp.rect(-bw / 2, 1.5, bw / 2, 1.5 + bh, "F.SilkS", 0.12)
    fp.rect(-bw / 2, 1.5, bw / 2, 1.5 + bh, "F.Fab", 0.10)
    fp.circle(-x, d["pad"] / 2 + 1.1, 0.35, "F.SilkS", 0.12, "solid")
    fp.rect(-bw / 2 - 0.5, -d["pad"] / 2 - 0.5, bw / 2 + 0.5, 1.5 + bh + 0.5, "F.CrtYd")
    return fp


def axial_mpc71() -> FP:
    fp = FP(
        "R_Axial_MPC71_3W",
        "Alternate 3 W non-inductive axial (Vishay MPC71 class). 22.5 mm pitch. "
        "Prefer R_TO220-2_PWR221T. Body is a courtyard estimate; confirm the "
        "specific axial MPN before using. No 3D: hand-formed leads.",
        "axial resistor 3W FS3W",
    )
    span = 22.5
    fp.prop("Reference", "REF**", 0, 4.5, "F.SilkS")
    fp.prop("Value", "R_Axial_MPC71_3W", 0, -3.5, "F.Fab")
    fp.pad(1, -span / 2, 0, 2.2, 2.2, 1.10)
    fp.pad(2, span / 2, 0, 2.2, 2.2, 1.10)
    fp.rect(-8.0, -2.2, 8.0, 2.2, "F.SilkS", 0.12)
    fp.line(-span / 2 + 1.2, 0, -8.0, 0, "F.SilkS", 0.12)
    fp.line(8.0, 0, span / 2 - 1.2, 0, "F.SilkS", 0.12)
    fp.circle(-span / 2, 2.0, 0.35, "F.SilkS", 0.12, "solid")
    fp.rect(-span / 2 - 1.5, -3.0, span / 2 + 1.5, 3.0, "F.CrtYd")
    return fp


def film(name: str, d: dict, descr: str) -> FP:
    fp = FP(name, descr, "film capacitor WIMA FS3W")
    x = d["pitch"] / 2
    fp.prop("Reference", "REF**", 0, d["body_w"] / 2 + 1.4, "F.SilkS")
    fp.prop("Value", name, 0, -d["body_w"] / 2 - 1.4, "F.Fab")
    fp.pad(1, -x, 0, d["pad"], d["pad"], d["drill"])
    fp.pad(2, x, 0, d["pad"], d["pad"], d["drill"])
    fp.rect(-d["body_l"] / 2, -d["body_w"] / 2, d["body_l"] / 2, d["body_w"] / 2, "F.SilkS", 0.12)
    fp.rect(-d["body_l"] / 2, -d["body_w"] / 2, d["body_l"] / 2, d["body_w"] / 2, "F.Fab", 0.10)
    fp.circle(-x, d["pad"] / 2 + 0.9, 0.30, "F.SilkS", 0.10, "solid")
    m = 0.5
    fp.rect(-d["body_l"] / 2 - m, -d["body_w"] / 2 - m,
            d["body_l"] / 2 + m, d["body_w"] / 2 + m, "F.CrtYd")
    return fp


def aircore() -> FP:
    d = AIRCORE
    fp = FP(
        "L_AirCore_12mm",
        "Hand-wound 2.2 uH air-core, 12 mm ID. Axes of the three channel "
        "inductors must be perpendicular and >= 25 mm apart (docs/05 §5.4 r7). "
        "Silk AXIS arrow is the coil axis. No 3D: hand-wound.",
        "air-core inductor FS3W",
    )
    x = d["lead_sep"] / 2
    fp.prop("Reference", "REF**", 0, d["od"] / 2 + 2.0, "F.SilkS")
    fp.prop("Value", "L_AirCore_12mm", 0, -d["od"] / 2 - 2.0, "F.Fab")
    fp.pad(1, -x, 0, d["pad"], d["pad"], d["drill"])
    fp.pad(2, x, 0, d["pad"], d["pad"], d["drill"])
    fp.circle(0, 0, d["od"] / 2, "F.SilkS", 0.12)
    fp.circle(0, 0, d["id"] / 2, "F.SilkS", 0.10)
    fp.circle(0, 0, d["od"] / 2, "F.Fab", 0.10)
    fp.line(0, -d["id"] / 2 + 0.5, 0, d["id"] / 2 - 0.5, "F.SilkS", 0.12)
    fp.text("AXIS", 3.2, 0, "F.SilkS", 0.7)
    fp.circle(-x, d["pad"] / 2 + 1.0, 0.30, "F.SilkS", 0.10, "solid")
    # 25 mm separation is between coils, not a courtyard of one coil.
    fp.rect(-d["od"] / 2 - 0.5, -d["od"] / 2 - 0.5,
            d["od"] / 2 + 0.5, d["od"] / 2 + 0.5, "F.CrtYd")
    fp.text(">=25mm to other L", 0, d["od"] / 2 + 3.2, "Dwgs.User", 0.7)
    return fp


def etd44() -> FP:
    d = ETD44
    fp = FP(
        "XFMR_ETD44",
        "Ferroxcube CPH-ETD44-1S-18P horizontal 18-pin bobbin + ETD44 core. "
        "Pin 1 is the leftmost pin of the -Y row. No copper pour under the "
        "core legs (keepout zones). No 3D: wind-your-own; STEP in phase 6.",
        "ETD44 transformer FS3W",
    )
    n = d["n_per_row"]
    pitch = d["pitch"]
    xs = [-(n - 1) / 2 * pitch + i * pitch for i in range(n)]
    y_row = d["row_sep"] / 2
    fp.prop("Reference", "REF**", 0, d["body_y"] / 2 + 2.0, "F.SilkS")
    fp.prop("Value", "XFMR_ETD44", 0, -d["body_y"] / 2 - 2.0, "F.Fab")
    # Pins 1-9 along -Y row (left to right = 1 to 9). Pins 10-18 along +Y
    # row right to left so pin 10 is opposite pin 9 (IEC transformer numbering).
    for i, x in enumerate(xs):
        fp.pad(i + 1, x, -y_row, d["pad"], d["pad"], d["drill"])
    for i, x in enumerate(reversed(xs)):
        fp.pad(10 + i, x, y_row, d["pad"], d["pad"], d["drill"])
    bx, by = d["body_x"] / 2, d["body_y"] / 2
    fp.rect(-bx, -by, bx, by, "F.SilkS", 0.12)
    fp.rect(-bx, -by, bx, by, "F.Fab", 0.10)
    fp.circle(xs[0], -y_row - 2.0, 0.40, "F.SilkS", 0.12, "solid")
    # Core outline and leg keepouts (no pour = shorted turn in leakage field).
    cl, ct = d["core_len"] / 2, d["core_thk"] / 2
    fp.rect(-cl, -ct, cl, ct, "F.Fab", 0.10)
    fp.rect(-cl, -ct, cl, ct, "Dwgs.User", 0.15)
    # Outer legs of an ETD sit at the ends of the 44 mm axis.
    leg = 8.0
    fp.keepout(-cl, -ct, -cl + leg, ct, "core_leg_neg")
    fp.keepout(cl - leg, -ct, cl, ct, "core_leg_pos")
    fp.text("NO POUR UNDER LEGS", 0, ct + 2.5, "Dwgs.User", 0.8)
    fp.rect(-bx - 0.5, -by - 0.5, bx + 0.5, by + 0.5, "F.CrtYd")
    return fp


def fuse_ato() -> FP:
    d = FUSE
    fp = FP(
        "Fuse_ATO_Blade",
        "Littelfuse 178.6165.0001 PCB ATO holder, 4-pin, 30 A. Pins 1+2 are "
        "one terminal (5.8 mm pair), pins 3+4 the other, 20 mm apart. "
        "0FHM0002XP is an in-line wire holder and is not this footprint. "
        "No 3D: vendor STEP not in-tree; body courtyard from the datasheet.",
        "ATO fuse holder FS3W",
    )
    ts, ps = d["term_sep"] / 2, d["pin_sep"] / 2
    fp.prop("Reference", "REF**", 0, d["body_w"] / 2 + 1.8, "F.SilkS")
    fp.prop("Value", "Fuse_ATO_Blade", 0, -d["body_w"] / 2 - 1.8, "F.Fab")
    # Terminal A = pins 1,2 (left); terminal B = pins 3,4 (right).
    fp.pad(1, -ts, -ps, d["pad"], d["pad"], d["drill"])
    fp.pad(2, -ts, ps, d["pad"], d["pad"], d["drill"])
    fp.pad(3, ts, -ps, d["pad"], d["pad"], d["drill"])
    fp.pad(4, ts, ps, d["pad"], d["pad"], d["drill"])
    bl, bw = d["body_l"] / 2, d["body_w"] / 2
    fp.rect(-bl, -bw, bl, bw, "F.SilkS", 0.12)
    fp.rect(-bl, -bw, bl, bw, "F.Fab", 0.10)
    fp.circle(-ts, -ps - 2.0, 0.35, "F.SilkS", 0.12, "solid")
    fp.rect(-bl - 0.5, -bw - 0.5, bl + 0.5, bw + 0.5, "F.CrtYd")
    return fp


def emit_busbar(name: str, w: float, l: float) -> str:
    # Busbars are SMD copper, not through-hole.
    descr = (
        f"Mask-free {w:g}x{l:g} mm copper for a soldered 2.5 mm2 busbar "
        "(docs/05 §5.2). No paste. Assign the net in layout. No 3D: copper feature."
    )
    return f'''(footprint "{name}"
  (version {KICAD_FP_VER})
  (generator "fs3w_gen_lib")
  (layer "F.Cu")
  (descr "{descr}")
  (tags "busbar FS3W")
  (attr smd)
  (property "Reference" "REF**"
    (at 0 {mm(l / 2 + 1.6)} 0)
    (layer "F.SilkS")
    (uuid "{uid(name, "ref")}")
    (effects (font (size 1 1) (thickness 0.15)))
  )
  (property "Value" "{name}"
    (at 0 {mm(-l / 2 - 1.6)} 0)
    (layer "F.Fab")
    (uuid "{uid(name, "val")}")
    (effects (font (size 1 1) (thickness 0.15)))
  )
  (pad "1" smd rect
    (at 0 0)
    (size {mm(w)} {mm(l)})
    (layers "F.Cu" "F.Mask")
    (uuid "{uid(name, "pad")}")
  )
  (fp_rect
    (start {mm(-w / 2)} {mm(-l / 2)})
    (end {mm(w / 2)} {mm(l / 2)})
    (stroke (width 0.12) (type solid))
    (fill none)
    (layer "F.SilkS")
    (uuid "{uid(name, "silk")}")
  )
  (fp_rect
    (start {mm(-w / 2 - 0.25)} {mm(-l / 2 - 0.25)})
    (end {mm(w / 2 + 0.25)} {mm(l / 2 + 0.25)})
    (stroke (width 0.05) (type solid))
    (fill none)
    (layer "F.CrtYd")
    (uuid "{uid(name, "crtyd")}")
  )
)
'''


def no3d_wall(pkg: str, case: str) -> str:
    return (
        f"{pkg} standing, tab to the heatsink wall, pad row 8.0 mm inboard of "
        f"the board edge (docs/05 §5.4). {case}. Pad 1 is leftmost when facing "
        "the printed face from the board interior (tab against the wall). "
        "No 3D: stock TO models sit flat on the board; wall-mount STEP is a "
        "phase 6 chassis-CAD deliverable."
    )


def all_footprints() -> dict[str, str]:
    out: dict[str, str] = {}
    out["TO-3P_Vertical_HeatsinkWall"] = wall_mount(
        "TO-3P_Vertical_HeatsinkWall", TO3P,
        no3d_wall("TO-3P", "onsemi CASE 340AB, pitch 5.45 BSC"),
    ).emit()
    out["TO-220-3_Vertical_HeatsinkWall"] = wall_mount(
        "TO-220-3_Vertical_HeatsinkWall", TO220,
        no3d_wall("TO-220-3", "JEDEC TO-220AB, pitch 2.54"),
    ).emit()
    out["TO-126N_Vertical_HeatsinkWall"] = wall_mount(
        "TO-126N_Vertical_HeatsinkWall", TO126,
        no3d_wall("TO-126N", "Toshiba 2-8U1A, pitch 2.29"),
    ).emit()
    out["TO-247-3_Vertical_HeatsinkWall"] = wall_mount(
        "TO-247-3_Vertical_HeatsinkWall", TO247,
        no3d_wall("TO-247-3", "ST TO-247, pitch 5.44; PSU rectifiers"),
    ).emit()
    out["R_TO220-2_PWR221T"] = pwr221().emit()
    out["R_Axial_MPC71_3W"] = axial_mpc71().emit()
    out["C_Film_5mm_P5.00mm"] = film(
        "C_Film_5mm_P5.00mm", FILM5,
        "WIMA MKS2 class, 5.00 mm pitch. Body courtyard is typical 7.2x4.5 mm; "
        "measure the fitted MPN. No 3D: many body heights in the series.",
    ).emit()
    out["C_Film_P10.00mm"] = film(
        "C_Film_P10.00mm", FILM10,
        "WIMA MKS4 1 u 100 V class, 10.00 mm pitch. No 3D: series body varies.",
    ).emit()
    out["C_Film_10mm_P15.00mm"] = film(
        "C_Film_10mm_P15.00mm", FILM15,
        "WIMA MKS4 2u2 class, 15.00 mm pitch (name kept from docs/07). "
        "No 3D: series body varies.",
    ).emit()
    out["L_AirCore_12mm"] = aircore().emit()
    out["XFMR_ETD44"] = etd44().emit()
    out["Fuse_ATO_Blade"] = fuse_ato().emit()
    out["Busbar_Pad_12x40"] = emit_busbar("Busbar_Pad_12x40", 12.0, 40.0)
    out["Busbar_Pad_15x50"] = emit_busbar("Busbar_Pad_15x50", 15.0, 50.0)
    out["Busbar_Pad_15x30"] = emit_busbar("Busbar_Pad_15x30", 15.0, 30.0)
    return out


# ---------------------------------------------------------------------------
# Symbols. Pin numbers from the datasheets, names from channel_netlist.py.
# ---------------------------------------------------------------------------

def pin(kind, name, number, x, y, rot, length=2.54) -> str:
    # rot 0 = pin points left (body on the right of the pin end)
    return f'''      (pin {kind} line (at {mm(x)} {mm(y)} {rot}) (length {mm(length)})
        (name "{name}" (effects (font (size 1.27 1.27))))
        (number "{number}" (effects (font (size 1.27 1.27))))
      )'''


def rectangle(x1, y1, x2, y2) -> str:
    return f'''      (rectangle (start {mm(x1)} {mm(y1)}) (end {mm(x2)} {mm(y2)})
        (stroke (width 0.254) (type default))
        (fill (type background))
      )'''


def prop(key, val, x, y, hide=False) -> str:
    h = " (hide yes)" if hide else ""
    return f'''    (property "{key}" "{val}" (at {mm(x)} {mm(y)} 0){h}
      (effects (font (size 1.27 1.27)))
    )'''


def ina1651_symbol() -> str:
    # TI SBOS818 pinout, INA1651 PW (TSSOP-14). Names match channel_netlist.
    pins = "\n".join([
        pin("power_in", "VCC", "1", 0, 12.7, 270),
        pin("input", "IN+", "2", -12.7, 7.62, 0),
        pin("input", "COM", "3", -12.7, 2.54, 0),
        pin("input", "IN-", "4", -12.7, 5.08, 0),
        pin("no_connect", "NC", "5", 12.7, -7.62, 180),
        pin("no_connect", "NC", "6", 12.7, -10.16, 180),
        pin("no_connect", "NC", "7", -12.7, -7.62, 0),
        pin("no_connect", "NC", "8", -12.7, -10.16, 0),
        pin("no_connect", "NC", "9", 12.7, -5.08, 180),
        pin("output", "VMID_OUT", "10", 12.7, 0, 180),
        pin("input", "VMID_IN", "11", -12.7, -2.54, 0),
        pin("input", "REF", "12", -12.7, 0, 0),
        pin("output", "OUT", "13", 12.7, 5.08, 180),
        pin("power_in", "VEE", "14", 0, -12.7, 90),
    ])
    return f'''  (symbol "INA1651"
    (exclude_from_sim no) (in_bom yes) (on_board yes)
    (property "Reference" "U" (at 0 17.78 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "INA1651" (at 0 15.24 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "Package_SO:TSSOP-14_4.4x5mm_P0.65mm" (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (property "Datasheet" "https://www.ti.com/lit/ds/symlink/ina1651.pdf" (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (property "Description" "TI INA1651 single balanced line receiver, TSSOP-14. Pin numbers from SBOS818 §5." (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (symbol "INA1651_0_1"
{rectangle(-10.16, 10.16, 10.16, -10.16)}
    )
    (symbol "INA1651_1_1"
{pins}
    )
  )'''


def ina1650_symbol() -> str:
    # Dual: unit A = ch A, unit B = ch B, unit C = power + VMID.
    def unit_ch(unit: str, inp, inn, com, ref, out) -> str:
        pins = "\n".join([
            pin("input", "IN+", inp, -12.7, 5.08, 0),
            pin("input", "IN-", inn, -12.7, 2.54, 0),
            pin("input", "COM", com, -12.7, 0, 0),
            pin("input", "REF", ref, -12.7, -2.54, 0),
            pin("output", "OUT", out, 12.7, 2.54, 180),
        ])
        return f'''    (symbol "INA1650_{unit}_0"
{rectangle(-10.16, 7.62, 10.16, -5.08)}
    )
    (symbol "INA1650_{unit}_1"
{pins}
    )'''

    pwr = "\n".join([
        pin("power_in", "VCC", "1", 0, 7.62, 270),
        pin("output", "VMID_OUT", "10", 12.7, 0, 180),
        pin("input", "VMID_IN", "11", -12.7, 0, 0),
        pin("power_in", "VEE", "14", 0, -7.62, 90),
    ])
    return f'''  (symbol "INA1650"
    (pin_names (offset 1.016))
    (exclude_from_sim no) (in_bom yes) (on_board yes)
    (property "Reference" "U" (at 0 10.16 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "INA1650" (at 0 7.62 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "Package_SO:TSSOP-14_4.4x5mm_P0.65mm" (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (property "Datasheet" "https://www.ti.com/lit/ds/symlink/ina1650.pdf" (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (property "Description" "TI INA1650 dual balanced line receiver, TSSOP-14. Pin numbers from SBOS818 §5. Unit A = ch A, B = ch B, C = power/VMID." (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
{unit_ch("1", "2", "4", "3", "12", "13")}
{unit_ch("2", "7", "5", "6", "9", "8")}
    (symbol "INA1650_3_0"
{rectangle(-10.16, 5.08, 10.16, -5.08)}
    )
    (symbol "INA1650_3_1"
{pwr}
    )
  )'''


def sg3525a_symbol() -> str:
    # onsemi SG3525A DIP/SOIC-16, same die. Pins 1-16.
    left = [
        ("input", "INV", "1", 7.62),
        ("input", "NI", "2", 5.08),
        ("input", "SYNC", "3", 2.54),
        ("output", "OSC", "4", 0),
        ("passive", "CT", "5", -2.54),
        ("passive", "RT", "6", -5.08),
        ("passive", "DISCH", "7", -7.62),
        ("passive", "SS", "8", -10.16),
    ]
    right = [
        ("passive", "COMP", "9", -10.16),
        ("input", "SHDN", "10", -7.62),
        ("output", "OUTA", "11", -5.08),
        ("power_in", "GND", "12", -2.54),
        ("power_in", "VC", "13", 0),
        ("output", "OUTB", "14", 2.54),
        ("power_in", "VIN", "15", 5.08),
        ("power_out", "VREF", "16", 7.62),
    ]
    pins = "\n".join(
        [pin(k, n, num, -15.24, y, 0) for k, n, num, y in left]
        + [pin(k, n, num, 15.24, y, 180) for k, n, num, y in right]
    )
    return f'''  (symbol "SG3525A"
    (exclude_from_sim no) (in_bom yes) (on_board yes)
    (property "Reference" "U" (at 0 13.97 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "SG3525A" (at 0 11.43 0)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm" (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (property "Datasheet" "https://www.onsemi.com/pdf/datasheet/sg3525a-d.pdf" (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (property "Description" "onsemi SG3525A PWM controller. Pin numbers from SG3525A-D. Order SG3525ADWR2G (SOIC-16W)." (at 0 0 0) (hide yes)
      (effects (font (size 1.27 1.27))))
    (symbol "SG3525A_0_1"
{rectangle(-12.7, 11.43, 12.7, -12.7)}
    )
    (symbol "SG3525A_1_1"
{pins}
    )
  )'''


def symbol_lib() -> str:
    return f'''(kicad_symbol_lib
  (version {KICAD_SYM_VER})
  (generator "fs3w_gen_lib")
{ina1651_symbol()}
{ina1650_symbol()}
{sg3525a_symbol()}
)
'''


README_TEXT = """# FS3W KiCad library (Phase 1)

Generated by `python3 tools/gen_lib.py`. Do not hand-edit the `.kicad_mod` or
`.kicad_sym` files; change the generator and re-run.

`python3 tools/check_lib.py` is the Phase 1 gate: it re-parses every footprint
and asserts pad-1 position and pitch against the datasheet constants.

## Pad-1 orientation (verified)

Wall-mount convention, all three-lead packages: **origin at the centre pin
(pad 2), pad 1 at negative X.** Looking from the board interior toward the
heatsink wall, with the tab against the wall and the printed face toward you,
pad 1 is on the left. That is the datasheet front-view pin 1.

The pad row is **8.0 mm inboard of the board edge**, locked by the heatsink
drill table in `docs/05` §5.4. Place the footprint with its origin on that
pad-row coordinate; the `EDGE` drawing line then sits on the board outline.

| Footprint | Pad 1 | Pitch (mm) | Source |
|---|---|---|---|
| `TO-3P_Vertical_HeatsinkWall` | left / B (NPN & PNP) | 5.45 BSC | onsemi CASE 340AB (NJW0281G) |
| `TO-220-3_Vertical_HeatsinkWall` | left / B or G | 2.54 | JEDEC TO-220AB |
| `TO-126N_Vertical_HeatsinkWall` | left / B | 2.29 | Toshiba 2-8U1A / TO-126N |
| `TO-247-3_Vertical_HeatsinkWall` | left / A1 | 5.44 | ST TO-247 (PSU rectifiers) |
| `R_TO220-2_PWR221T` | left | 5.08 | Bourns PWR221T-20 |
| `R_Axial_MPC71_3W` | left | 22.5 | alternate only |
| `C_Film_5mm_P5.00mm` | left | 5.00 | WIMA MKS2 |
| `C_Film_P10.00mm` | left | 10.00 | WIMA MKS4 1 µ |
| `C_Film_10mm_P15.00mm` | left | 15.00 | WIMA MKS4 2µ2 (docs/07 name) |
| `L_AirCore_12mm` | left | 12.0 lead sep. | hand-wound, 12 mm ID |
| `XFMR_ETD44` | pin 1 = leftmost of −Y row | 5.08 / 35.56 row | Ferroxcube CPH-ETD44-1S-18P |
| `Fuse_ATO_Blade` | pin 1 = left terminal, −Y of pair | 20.0 / 5.8 | Littelfuse 178.6165.0001 |
| `Busbar_Pad_*` | single SMD copper | — | docs/05 §5.2 |

Transistor pin function is in the **symbol**, not the footprint. TO-220-3 is
shared by `MJE15032G` (BCE) and `IRFB4110` (GDS).

## Symbols (pin numbers from datasheets)

| Symbol | Package | Pin source | Names used by `channel_netlist.py` |
|---|---|---|---|
| `INA1651` | TSSOP-14 | TI SBOS818 §5 | `IN+`(2) `IN-`(4) `COM`(3) `REF`(12) `VMID_IN`(11) `VMID_OUT`(10) `OUT`(13) `VCC`(1) `VEE`(14). Pins 5–9 NC |
| `INA1650` | TSSOP-14 | TI SBOS818 §5 | Unit A: 2/4/3/12/13. Unit B: 7/5/6/9/8. Unit C: VCC(1) VEE(14) VMID_IN(11) VMID_OUT(10) |
| `SG3525A` | SOIC-16W | onsemi SG3525A-D | INV 1, NI 2, SYNC 3, OSC 4, CT 5, RT 6, DISCH 7, SS 8, COMP 9, SHDN 10, OUTA 11, GND 12, VC 13, OUTB 14, VIN 15, VREF 16 |

`COM` treatment (docs/02 and AGENT_BRIEF): `COM` and `REF` tie to `SIG_GND`.
The 1 MΩ `R7` from `COM` to `SIG_GND` is DNP; SBOS818 §8.1.3 says that
resistor is **in series with COM**, not in parallel with a hard COM-to-ground
bond. The hard bond is what gives the 91 dB CMRR figure. Leave `R7` DNP unless
a measured source-impedance mismatch says otherwise.

## 3D models

None of these footprints ship a 3D model, on purpose:

| Kind | Why there is no 3D |
|---|---|
| Wall-mount TO-3P / TO-220 / TO-126N / TO-247 | Stock KiCad models sit flat on the board. These parts stand with the tab on the chassis wall and the body off the board edge. A useful STEP comes from the chassis CAD in phase 6. |
| `R_TO220-2_PWR221T` | Stock TO-220-3 models have a tab pin this package does not have. |
| Film capacitors, air-core, transformer, fuse | Body height varies by MPN, or the part is hand-wound. |
| Busbar pads | Copper features, not components. |

## Not in this library (do not invent)

- **Omron `G4A-1A-PE DC12`.** Unique pin pattern, not G8P. Footprint waits on a
  traced Omron mechanical drawing. Guessing it costs a board spin.
- Stock SMD (0805, TSSOP-14, SOIC-8, SOT-23, SOT-363) — use KiCad system libs.

## Regenerating

```bash
python3 tools/gen_lib.py
python3 tools/check_lib.py
```
"""


def main() -> None:
    PRETTY.mkdir(parents=True, exist_ok=True)
    fps = all_footprints()
    for name, text in fps.items():
        (PRETTY / f"{name}.kicad_mod").write_text(text, encoding="utf-8")
    SYM.parent.mkdir(parents=True, exist_ok=True)
    SYM.write_text(symbol_lib(), encoding="utf-8")
    README.write_text(README_TEXT, encoding="utf-8")
    print(f"wrote {len(fps)} footprints -> {PRETTY}")
    print(f"wrote {SYM.name}")
    print(f"wrote {README.name}")


if __name__ == "__main__":
    main()
