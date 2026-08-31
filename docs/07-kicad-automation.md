# 07 — Building the Schematic and PCB Programmatically

## 7.1 The constraint that shapes everything

**KiCad has no schematic API, not even in KiCad 10.** The IPC API introduced in KiCad 9
covers the PCB editor only; the `10.0` branch of `schematic_commands.proto` defines zero
commands, and the schematic type model exists only on KiCad 11 development branches.
Anyone claiming to script KiCad schematics through the official API is describing
something that does not exist yet.

So the two halves of the job use different mechanisms:

| Task | Mechanism | Requires KiCad running? |
|---|---|---|
| Generate schematic | write `.kicad_sch` S-expressions via `kicad-sch-api` | no |
| Export netlist / ERC / BOM | `kicad-cli sch ...` | no |
| Place footprints | `pcbnew` SWIG bindings (KiCad 9/10) or IPC API (KiCad 11+) | SWIG: no. IPC: yes, or `kicad-cli api-server` |
| Route | scripted track placement for critical nets, manual for the rest | no |
| DRC, gerbers, BOM, CPL | `kicad-cli pcb ...` | no |

**Use KiCad 9.x or 10.x, not 11.** The SWIG `pcbnew` bindings let a script open a
`.kicad_pcb`, place footprints and lay tracks with no GUI and no IPC server. They are
removed in KiCad 11, where the same work needs `kicad-cli api-server` plus `kicad-python`.
Both work; 9/10 is simpler and better documented today.

## 7.2 Toolchain setup

Nothing is currently installed in this workspace — no KiCad, no `pcbnew`, no `ngspice`.

```bash
# KiCad 9 or 10 (Arch / CachyOS)
sudo pacman -S kicad kicad-library kicad-library-3d ngspice

# verify the version and that the Python bindings came with it
kicad-cli version
python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"
```

`pcbnew` is provided by the KiCad package and is bound to the system Python. If you work
in a virtualenv, create it with `--system-site-packages` or `import pcbnew` will fail.

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r tools/requirements.txt
```

### Alternative: atopile

[`atopile`](https://github.com/atopile/atopile) is a genuine code-first EDA toolchain —
declarative `.ato` modules with units, tolerances and assertions, compiling to a KiCad
project, and as of 2026 it ships its own browser-based layout editor. It is a good fit
for the *constraint checking* side of this project: you could express "rail voltage ×
peak current ≤ device SOA" as an assertion the compiler enforces.

It is **not** recommended as the primary path here, for two reasons. Its parametric part
picker targets catalogue parts, and almost nothing in this design is a catalogue part
(TO-3P audio transistors, a hand-wound ETD44 transformer, 0.22 Ω 3 W non-inductive
ballast resistors). More importantly, you asked for a schematic, and the value of a real
hierarchical `.kicad_sch` is that a human can review the analogue design before any
copper is committed. Generating S-expressions gives you that; a netlist-only flow does
not.

## 7.3 Source of truth

```
tools/channel_netlist.py      one amplifier channel: 99 components, 65 nets,
                              227 connections, self-validating
tools/design_calcs.py         every electrical and mechanical number
docs/05-pcb-layout.md §5.4    board outline, regions, device row coordinates
```

`channel_netlist.py --check` currently reports 0 errors and 0 warnings. It verifies that
every declared pin is connected, no pin is on two nets, no net has a single connection,
and every net has a net class. **Run it in CI and before every generation step.** A
netlist error caught here costs seconds; caught at bring-up it costs a board.

```bash
python3 tools/channel_netlist.py --check     # gate
python3 tools/channel_netlist.py --stats     # 90 physical parts per channel
python3 tools/channel_netlist.py --netlist   # flat KiCad netlist, one channel
```

## 7.4 Phase plan

Each phase has an exit gate. Do not proceed past a failed gate.

### Phase 0 — Simulate, before anything else

The single highest-value step, and the one most likely to be skipped. A three-stage
amplifier with a beta-enhanced VAS has two ways to be subtly wrong (compensation and
clipping recovery) that a schematic review will not catch.

Build the channel in `ngspice` from `channel_netlist.py`, and run the seven checks in
`docs/02-amplifier-channel.md` §2.6.

**Gate:** ≥ 60° phase margin and ≥ 10 dB gain margin into every load including
2 Ω ∥ 2.2 µF; THD below 0.005 % at 1 kHz half power; clean clipping recovery; quiescent
current stable from 25 °C to 90 °C.

**Status: the amplifier channel is done and passes.** Results and the measured tables are
in `docs/02` §2.3, and §2.6 records what was run and the two ngspice traps that produce
plausible wrong answers. Item 7 of §2.6, compensation sensitivity to `TTC004B` Cob
tolerance, is still outstanding. Note the gate no longer names a target unity-loop-gain
frequency: the earlier "2.28 MHz" conflated open-loop unity gain with loop unity gain,
which are a factor of 1/β = 20 apart. The design measures 8.3 MHz and 456 kHz
respectively, and what the gate should be checking is the margins, not a frequency.

The PSU control loop has not been simulated yet; it still needs a separate run for phase
margin at the 3–5 kHz crossover.

### Phase 1 — Symbol and footprint libraries

Custom footprints needed, none of which exist in the stock libraries in the form this
design requires:

| Footprint | Notes |
|---|---|
| `FS3W:TO-3P_Vertical_HeatsinkWall` | vertical, tab to wall, 5.45 mm pad pitch, courtyard extending to the board edge, keepout for the M3 bolt and the mounting boss |
| `FS3W:TO-220-3_Vertical_HeatsinkWall` | same convention |
| `FS3W:TO-126N_Vertical_HeatsinkWall` | Toshiba TO-126N is 8.0 × 11 × 3.25 mm |
| `FS3W:TO-247-3_Vertical_HeatsinkWall` | PSU rectifiers, same wall-mount convention |
| `FS3W:R_TO220-2_PWR221T` | Bourns PWR221T-20 / Caddock MP930; this is what the BoM actually orders |
| `FS3W:R_Axial_MPC71_3W` | alternate only — axial 3 W non-inductive |
| `FS3W:C_Film_5mm_P5.00mm`, `FS3W:C_Film_P10.00mm`, `FS3W:C_Film_10mm_P15.00mm` | film capacitors, 5 / 10 / 15 mm pitch |
| `FS3W:L_AirCore_12mm` | output inductor, 12 mm ID, with a keepout annotation recording the ≥ 25 mm separation and perpendicular-axis rule |
| `FS3W:XFMR_ETD44` | 18-pin CPH-ETD44-1S-18P, with the no-pour-under-core-legs keepout |
| `FS3W:Busbar_Pad_*` | mask-free reinforcement rectangles |
| `FS3W:Fuse_ATO_Blade` | Littelfuse 178.6165.0001 PCB 4-pin ATO holder |

**Status: generated.** `python3 tools/gen_lib.py` writes `lib/FS3W.pretty` and `lib/FS3W.kicad_sym`. `python3 tools/check_lib.py` is the gate: pad-1 at −X, pitches match the datasheet constants, symbols present. Pad-1 orientation and the 3D-model reasons are in `lib/README.md`.

**Not invented:** Omron `G4A-1A-PE DC12` waits on a traced mechanical drawing. Do not use a G8P footprint.

Symbols: `INA1650`/`INA1651`/`SG3525A` are in `lib/FS3W.kicad_sym`. Pin numbers were taken
from TI SBOS818 §5 and onsemi SG3525A-D, not from Ultra Librarian. **A wrong pin number
on a TSSOP-14 costs a board spin** — `tools/check_lib.py` asserts the symbol file contains
those pin names.

**Gate: passed.** `python3 tools/check_lib.py`. Pad-1 at −X; pitches match datasheet
constants; 3D-model reasons are in `lib/README.md`.

### Phase 2 — Generate the schematic

Hierarchical structure:

```
fs3w-amp.kicad_sch                root: sheet instances, rail symbols, interconnect
├── amp_channel.kicad_sch  ×3     one instance each: tweeter, mid, midbass
├── regulators.kicad_sch          ±30 V and ±15 V regulators
├── protection.kicad_sch          detectors, latch, sequencing, relays
└── interface.kicad_sch           input connectors, speaker terminals, PSU entry

fs3w-psu.kicad_sch                separate project
```

Annotation offsets give `R101…` / `R201…` / `R301…` per channel, matching
`docs/02-amplifier-channel.md`.

`tools/gen_schematic.py` should:

1. Import `COMPONENTS` and `NETLIST` from `channel_netlist.py`.
2. Run the validator and abort on any error.
3. Place symbols on a 1.27 mm grid in functional clusters, laid out left to right in
   signal order: receiver → trim → LTP → mirror → VAS → spreader → triple → output
   network, with the servo below and the decoupling in a column at the right.
4. Wire by net. For nets with more than four connections (`SIG_GND` 24, `OUT_STAR` 15,
   `VCC_FE` 10) use labels rather than wires — a 24-connection wire mesh is unreadable
   and unreviewable, which defeats the purpose of generating a schematic.
5. Emit hierarchical pins in the order given in `HIER_PINS`.
6. Write the sheet, then the root, then the instance data.

Practical notes on `kicad-sch-api`: positions are mandatory (there is no auto-place), it
does pin-to-pin orthogonal routing without collision detection, and it preserves KiCad's
formatting byte-for-byte. Budget real effort on the placement grid — this is where a
generated schematic becomes either reviewable or useless.

```bash
kicad-cli sch erc fs3w-amp.kicad_sch --exit-code-violations
kicad-cli sch export netlist fs3w-amp.kicad_sch -o fs3w-amp.net
kicad-cli sch export bom fs3w-amp.kicad_sch -o bom/generated-amp.csv
kicad-cli sch export pdf fs3w-amp.kicad_sch -o docs/schematic-amp.pdf
```

**Gate:** ERC clean apart from documented waivers; exported netlist matches
`channel_netlist.py --netlist` for one channel, compared net by net by a script, not by
eye; the PDF is legible and a human has actually reviewed the analogue sections.

### Phase 3 — Board setup and placement

1. Create `fs3w-amp.kicad_pcb`, import the netlist.
2. Apply the stackup from §5.1: 4 layers, **2 oz outer / 1 oz inner**, 1.6 mm.
3. Apply net classes from §5.2 programmatically — this is the mechanism that makes the
   trace widths self-enforcing through DRC rather than dependent on the router's
   diligence.
4. Draw the 240 × 160 mm outline with 3 mm corner radii, and the six M3 holes.
5. Place the 21 heatsink-mounted devices at the **exact coordinates in §5.4**. These are
   not suggestions — they define the heatsink drilling.
6. Place remaining footprints into their regions (A–G) following the placement rules.

```python
import pcbnew
board = pcbnew.LoadBoard("fs3w-amp.kicad_pcb")
fp = board.FindFootprintByReference("Q112")
fp.SetPosition(pcbnew.VECTOR2I_MM(22.95, 8.0))
fp.SetOrientationDegrees(0)
pcbnew.SaveBoard("fs3w-amp.kicad_pcb", board)
```

Emit the heatsink drilling drawing from the same coordinate table, so the board and the
metalwork cannot disagree.

**Gate:** `tools/check_layout.py` confirms device coordinates match the drill table
exactly; no footprint overlaps; all footprints inside their assigned region.

### Phase 4 — Routing

**Do not autoroute this board.** On a power amplifier the routing *is* the design: loop
areas, the Kelvin feedback tap, the single ground bridge and the `LC_A` node are all
things an autorouter will get wrong while reporting 100 % completion.

Route in this order, because each stage constrains the next:

1. **By script, from an explicit track list:** the star ground pad and its via array; the
   rail trunks; per-channel rail feeds; `OUT_STAR` copper regions; ballast resistor
   connections; speaker outputs. These are wide, geometric, and benefit from being
   generated and diffable.
2. **By script:** the L2 ground split polygons and the single 3 mm bridge.
3. **By hand or agent, one channel at a time:** the front-end cluster, `LC_A`, the
   spreader wiring, the feedback tap, the servo.
4. **Replicate** the validated channel-1 front-end routing to channels 2 and 3, either
   with KiCad's replicate-layout functionality or by scripted transform. Identical
   channels should have identical copper.
5. **Freerouting is acceptable for the protection block only** — low-current logic in
   region E, with everything else locked first.

### Phase 5 — Verification

```bash
kicad-cli pcb drc fs3w-amp.kicad_pcb --severity-error --exit-code-violations
python3 tools/check_layout.py fs3w-amp.kicad_pcb
```

`tools/check_layout.py` implements the checks standard DRC cannot express, from §5.7:

- no signal net crosses the L2 ground split
- exactly one copper bridge between `SIG_GND` and `PWR_GND`
- `R37` pad within 5 mm of the `OUT_STAR` ballast junction centroid
- per-channel output loop area under 15 cm²
- air-core inductor separation ≥ 25 mm, axes non-parallel
- device coordinates match the heatsink drill table
- no copper pour under the T1 core legs
- rail trunk minimum width ≥ 12 mm along its whole length

These are the checks that distinguish a board that works from a board that measures well.
Write them before you need them.

### Phase 6 — Outputs

```bash
kicad-cli pcb export gerbers fs3w-amp.kicad_pcb -o fab/amp/
kicad-cli pcb export drill   fs3w-amp.kicad_pcb -o fab/amp/
kicad-cli pcb export pos     fs3w-amp.kicad_pcb -o fab/amp/cpl.csv --format csv
kicad-cli pcb export step    fs3w-amp.kicad_pcb -o mech/amp.step
kicad-cli pcb export pdf     fs3w-amp.kicad_pcb -o docs/pcb-amp.pdf
```

The STEP export feeds the chassis and heatsink design; verify device tab positions
against the chassis walls in CAD before ordering metalwork.

## 7.5 Repository layout to build toward

```
fs3w/
├── tools/
│   ├── design_calcs.py          done
│   ├── channel_netlist.py       done
│   ├── requirements.txt         done
│   ├── gen_schematic.py         phase 2
│   ├── place_pcb.py             phase 3
│   ├── route_power.py           phase 4
│   ├── check_layout.py          phase 5
│   └── export_fab.py            phase 6
├── lib/
│   ├── FS3W.kicad_sym
│   ├── FS3W.pretty/
│   └── 3d/
├── sim/
│   ├── channel.cir
│   ├── psu_loop.cir
│   └── run_all.sh
├── fs3w-amp/                    KiCad project
├── fs3w-psu/                    KiCad project
├── fab/
├── mech/
└── docs/
```

## 7.6 Guidance for the implementing agent

1. **Everything is regenerable.** Never hand-edit a generated file; change the generator
   and re-run. The moment `fs3w-amp.kicad_sch` is edited by hand, `channel_netlist.py`
   stops being the source of truth and the project loses its main safety property.
2. **Commit after every phase gate,** with the gate output in the commit message.
3. **The three channels must be identical.** If channel 2's front-end copper differs from
   channel 1's, that is a defect, not a variation.
4. **Ask rather than guess on these three:** the exact `INA1651` pin assignment and the
   `COM` pin treatment; the ETD44 window fill (move to ETD49 rather than thinning
   conductors); and the `SG3525A` frequency-setting components, which must be measured
   rather than calculated.
5. **Trace widths are not negotiable downward.** They are set by voltage drop, not
   thermal limits, and every milliohm in the output and ground paths costs damping factor.
6. **If a gate fails, stop and report.** Do not route around a failed simulation.
