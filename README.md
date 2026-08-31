# FS-3W — Three-Way Active Front-Stage Car Amplifier

A per-side, three-channel discrete Class-AB car amplifier designed for a fully active
three-way front stage. Two identical units are built: one for the left stage, one for
the right, so left and right share no power supply, no ground return and no chassis.

**Design priority: sound quality above cost, size, efficiency and feature count.**

---

## System at a glance

| | |
|---|---|
| Units required | 2 (one per side, identical) |
| Channels per unit | 3 — tweeter, midrange, midbass |
| Loads | tweeter 4 Ω, midrange 4 Ω, midbass 2 Ω |
| Topology | discrete Class AB, three-stage, EF3 output triple, 2 output pairs/channel |
| Rails | regulated ±24 V main, regulated ±30 V front-end, regulated ±15 V line-receiver |
| Power at clipping | 62 W / 4 Ω (tweeter), 62 W / 4 Ω (mid), 113 W / 2 Ω (midbass) |
| Stability | 89° phase margin, 13 dB gain margin, worst case of every load simulated |
| Inputs | electronically balanced, 91 dB CMRR, unity gain, per-channel gain trim |
| Crossovers | none on board — external DSP does all filtering and time alignment |
| Signal path | no electrolytics, no coupling cap in the feedback loop (DC servo) |
| Supply | separate PCB, regulated push-pull SMPS, ~250 W continuous, phase-locked pair |
| Boards per unit | 2 (amplifier board + SMPS board) |

Simulated, on the netlist generated from the design source of truth: 0.0013 % THD at
1 kHz / 52 W into 4 Ω, 0.0245 % at 20 kHz, 88.7° worst-case phase margin, zero step
overshoot into any resistive load. Full tables and the caveats that go with them are in
docs/02 §2.3. Still to be confirmed at bring-up, because simulation cannot speak to
them: SNR > 110 dB A-weighted referenced to full output, damping factor > 200 at 100 Hz,
and no switching residue above −90 dBV at the speaker terminals.

## Why these numbers

You asked for "around 50 W per channel, stable to 2 Ω". A single ±24 V rail delivers
62 W on the 4 Ω channels and 113 W on the 2 Ω midbass. That asymmetry is
deliberate and free: a three-way active front stage needs the most power exactly where
the 2 Ω driver sits, and the least on the tweeter. One rail voltage therefore produces a
naturally correct power distribution without any per-channel supply complexity.

If you would rather cap the midbass nearer 50 W, drop the main rail to ±16 V and rerun
`tools/design_calcs.py`; you will lose the 4 Ω channels down to about 25 W each, which
is why the design does not do this by default.

## Read in this order

| Document | Contents |
|---|---|
| [`docs/01-system-architecture.md`](docs/01-system-architecture.md) | Block diagram, rail plan, grounding architecture, signal levels, design decision log |
| [`docs/02-amplifier-channel.md`](docs/02-amplifier-channel.md) | Channel topology, every component value, and a complete pin-to-net table |
| [`docs/03-psu-board.md`](docs/03-psu-board.md) | Push-pull converter, transformer winding spec, regulation loop, filtering |
| [`docs/04-protection-and-control.md`](docs/04-protection-and-control.md) | DC-offset, thermal, overcurrent, turn-on sequencing, muting |
| [`docs/05-pcb-layout.md`](docs/05-pcb-layout.md) | Stackup, trace sizing, net classes, grounding, placement, thermal, mechanical |
| [`docs/06-bringup-and-test.md`](docs/06-bringup-and-test.md) | Staged power-up procedure, measurements, acceptance limits |
| [`docs/07-kicad-automation.md`](docs/07-kicad-automation.md) | Toolchain and how to build the schematic and PCB programmatically |
| [`AGENT_BRIEF.md`](AGENT_BRIEF.md) | Self-contained handoff prompt for the agent that implements the PCB |
| [`bom/`](bom/) | Bill of materials per board, with alternates and sourcing notes |
| [`tools/design_calcs.py`](tools/design_calcs.py) | Every quoted number, re-derivable |

## Regenerating the design numbers

```bash
python3 tools/design_calcs.py
```

No dependencies beyond the standard library. Change an input at the top of the file
(rail voltage, load impedance, output pairs, ambient temperature) and every derived
figure — power, dissipation, heatsink requirement, compensation, transformer turns,
trace widths — is recomputed.

## Parts availability warnings

The classic parts for this kind of amplifier are dying off. Verified as of this
revision:

- **onsemi ThermalTrak (`NJL3281D`/`NJL1302D`) is discontinued.** The February 2026
  datasheet revision marks both part numbers as such. The design therefore does not
  rely on output devices with integrated bias-tracking diodes; it uses a conventional
  Vbe multiplier bolted to the heatsink instead.
- **`KSA1381`/`KSC3503` are end-of-life.** These were the standard low-Cob VAS
  transistors. Toshiba `TTA004B`/`TTC004B` are used instead, and the compensation is
  designed around their higher 12–17 pF Cob from the start. Builders report instability
  when substituting these into existing designs compensated for 2 pF parts; designing
  for them avoids that failure mode. KEC `KTC3503`/`KTA1381` are a pin- and
  spec-compatible fallback if you prefer the original characteristics.
- **`NJW0281G`/`NJW0302G` output devices are active** and gain-matched to within 10 %
  between NPN and PNP from 50 mA to 3 A, which is the single most useful property an
  output pair can have.

## Status

Design specification complete and internally consistent. Nothing has been simulated,
laid out or built yet. `docs/06-bringup-and-test.md` and `docs/07-kicad-automation.md`
define the work remaining, in order.
