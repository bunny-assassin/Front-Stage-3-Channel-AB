# Agent Brief — Implement the FS-3W Amplifier PCBs

Self-contained handoff. Paste this to the agent that will do the schematic capture,
layout and fabrication outputs.

---

## Your task

Take the completed electrical design in this repository and produce fabrication-ready
KiCad projects for two PCBs: a three-channel discrete Class-AB car amplifier board and its
regulated push-pull SMPS board. Two identical units will be built, one per stereo side.

The electrical design is finished and validated for internal consistency. **You are not
being asked to redesign it.** You are being asked to realise it in KiCad, correctly,
with the layout constraints treated as hard requirements rather than preferences.

## Read these first, in order

| File | Why you need it |
|---|---|
| `README.md` | system overview and parts-availability warnings |
| `docs/01-system-architecture.md` | rail plan, grounding architecture, decision log |
| `docs/02-amplifier-channel.md` | full channel design and the authoritative pin-to-net table |
| `docs/03-psu-board.md` | converter design and transformer winding spec |
| `docs/04-protection-and-control.md` | protection block |
| `docs/05-pcb-layout.md` | **stackup, trace sizing, net classes, placement coordinates — the core of your job** |
| `docs/06-bringup-and-test.md` | what will be measured, so you know what the layout must achieve |
| `docs/07-kicad-automation.md` | **phase plan, toolchain, gates — follow this** |
| `bom/` | parts, with substitution warnings |

## Source of truth

```
tools/channel_netlist.py    one amplifier channel as validated data:
                            99 components, 65 nets, 227 connections
tools/design_calcs.py       every electrical, thermal and trace-width number
```

Both are standard-library-only Python. Run them:

```bash
python3 tools/channel_netlist.py --check     # must report 0 errors, 0 warnings
python3 tools/channel_netlist.py --stats
python3 tools/design_calcs.py
```

`channel_netlist.py` is the schematic. `docs/02` is its human-readable form. **If they
ever disagree, the Python wins, because it is the one that gets validated.** Generate the
schematic from it; never hand-edit generated files.

## Environment

Nothing is installed yet.

```bash
sudo pacman -S kicad kicad-library kicad-library-3d ngspice
python3 -m venv --system-site-packages .venv   # --system-site-packages or pcbnew won't import
source .venv/bin/activate
pip install -r tools/requirements.txt
```

**Use KiCad 9.x or 10.x, not 11.** KiCad 9/10 still ship the SWIG `pcbnew` bindings, which
let a script open a board, place footprints and lay tracks with no GUI and no IPC server.
KiCad 11 removes them and requires `kicad-cli api-server` plus `kicad-python`.

**There is no schematic API in any KiCad release, including 10.** Generate `.kicad_sch`
by writing S-expressions with `kicad-sch-api`. Do not waste time looking for a schematic
IPC endpoint; the `10.0` protobuf branch defines zero schematic commands.

## Phases and gates

Full detail in `docs/07-kicad-automation.md`. Do not pass a failed gate; stop and report.

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | ngspice model of one channel and the PSU loop | ≥ 60° phase margin and ≥ 10 dB gain margin into every load incl. 2 Ω ∥ 2.2 µF; THD < 0.005 % at 1 kHz half power; clean clipping recovery; bias stable 25–90 °C. **Channel done and passing** (88.7°, 13.1 dB, 0.0017 %); PSU loop still to do |
| 1 | `lib/FS3W.kicad_sym` and `FS3W.pretty` | every custom footprint's pad-1 orientation verified against the datasheet drawing |
| 2 | hierarchical schematic, 3 channel instances | ERC clean; exported netlist matches `--netlist` output net-by-net **by script**; PDF reviewed by a human |
| 3 | board outline, stackup, net classes, placement | heatsink device coordinates match the drill table exactly; no overlaps; all parts within their assigned region |
| 4 | routing | see routing rules below |
| 5 | verification | `kicad-cli pcb drc` clean plus all custom checks in `docs/05` §5.7 |
| 6 | gerbers, drill, CPL, STEP, PDF, heatsink drawing | STEP checked against chassis walls in CAD |

## Hard constraints — do not deviate

1. **Stackup is 4-layer, 2 oz outer, 1 oz inner.** No net over 3 A may rely on an inner
   layer. Specify this explicitly at the fab; the default offering will not carry these
   currents.
2. **Trace widths in `docs/05` §5.2 are minimums and are set by voltage drop, not thermal
   limits.** Never reduce them. Every milliohm in the output and ground paths costs
   damping factor.
3. **`SIG_GND` and `PWR_GND` are separate L2 regions joined by exactly one 3 mm bridge at
   the star point.** No signal net may cross the split. Standard DRC cannot catch this;
   write the check.
4. **`R37` (feedback upper leg) taps `OUT_STAR` at the ballast resistor junction**, on its
   own trace carrying no load current. This is a Kelvin connection.
5. **`R38` returns to `SIG_GND` by the shortest path to the star bridge.**
6. **Heatsink device coordinates in `docs/05` §5.4 are exact.** They define the chassis
   drilling. Emit the drill drawing from the same table so they cannot diverge.
7. **The three channels must be geometrically identical.** Validate channel 1's front-end
   routing, then replicate it. A difference between channels is a defect.
8. **Do not autoroute the amplifier board.** On a power amplifier the routing is the
   design. Freerouting is acceptable for the protection block only, with everything else
   locked first.
9. **Air-core output inductors: axes perpendicular, ≥ 25 mm apart.** Three parallel
   air-core coils are three coupled transformers.
10. **No copper pour under the T1 core legs** — that is a shorted turn in the leakage field.
11. **Output stage loop area under 15 cm² per polarity per channel.**
12. **Rail reservoirs sit between their channel's device rows**, not at the board edge.

## Routing order

1. Script the geometric power copper: star pad and via array, rail trunks, per-channel
   rail feeds, `OUT_STAR` regions, ballast connections, speaker outputs.
2. Script the L2 ground split polygons and the single bridge.
3. Hand-route (or agent-route) channel 1's front-end: the `LC_A` cluster, spreader wiring,
   feedback tap, servo. Keep `Q1`, `Q3`, `Q4`, `Q5` and `C9` within a 20 × 20 mm cluster —
   `LC_A` is the highest-impedance node in the amplifier and its stray capacitance changes
   the compensation.
4. Replicate to channels 2 and 3.
5. Protection block last.

## Ask, do not guess

Three items are genuinely uncertain and guessing wrong costs a board spin:

1. **`INA1651` pin assignment and the `COM` pin treatment.** It is TSSOP-14 with several
   NC pins. `docs/02` §2.1 records what the datasheet says and flags a DNP 1 MΩ option
   whose exact recommended connection needs confirming against datasheet §8.
2. **ETD44 window fill for the specified windings.** If it will not fit comfortably, move
   to ETD49 and keep the turns counts. Do **not** thin the conductors.
3. **`SG3525A` frequency-setting components.** The 65 kHz target must be measured on the
   actual board, not calculated.

## Working practices

- Commit after every phase gate, with the gate output in the commit message.
- Everything is regenerable. Change the generator, re-run, commit the result. The moment
  a generated file is hand-edited, `channel_netlist.py` stops being the source of truth
  and the project loses its main safety property.
- If a gate fails, stop and report. Do not route around a failed simulation.
- Record any deviation from this brief, with reasoning, in a `DEVIATIONS.md`.

## Context you should have about the design intent

This is a sound-quality-first design for a fully active three-way front stage, fed by an
external DSP that does all crossover and time-alignment work. Left and right are separate
units with separate supplies and grounds, so stereo separation is limited by the source
rather than by shared supply impedance.

The choices that look expensive or over-specified are load-bearing:

- The EF3 output triple and two output pairs per channel exist so the 2 Ω midbass channel
  does not load the VAS and does not push the output devices out of their linear hFE
  region.
- The separate regulated ±30 V front-end rail exists so the output stage can swing to
  within 2.2 V of the main rail and so the input stage never sees output-stage rail
  modulation.
- The DC servo exists to remove the last electrolytic from the feedback loop.
- The interwinding shield, the shielded board partition and the converter sync line
  between units all exist to keep 65 kHz switching residue below −90 dBV at the speaker
  terminals. That measurement in `docs/06` §6.6 is what validates the whole two-board
  architecture.

If a layout decision trades one of these away for convenience, it defeats the point of
the project. Raise it instead.
