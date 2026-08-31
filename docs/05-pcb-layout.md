# 05 — PCB Layout, Trace Sizing and Mechanical

Two boards per unit. This document is written to be executable: an implementing agent
should be able to derive every net class, width, clearance and placement region from it
without further judgement calls.

Regenerate every current-carrying number with `python3 tools/design_calcs.py`.

## 5.1 Stackup

Both boards use the same 4-layer stackup, 1.6 mm finished.

| Layer | Copper | Purpose |
|---|---|---|
| L1 (top) | **2 oz** | components, all high-current routing, output stages, rail trunks |
| L2 | 1 oz | ground reference, split into `SIG_GND` and `PWR_GND` regions |
| L3 | 1 oz | rail distribution (`VCC_FE`, `VEE_FE`, `VCC_15`, `VEE_15`) and low-current routing |
| L4 (bottom) | **2 oz** | high-current return copper, speaker outputs, supplementary rail copper |

**Hard rule: no high-current net (over 3 A) may rely on an inner layer.** Inner copper is
1 oz and IPC-2221 derates internal conductors by half, so 10 A on an internal 1 oz layer
would need 12.3 mm of width against 3.6 mm on 2 oz external. All power current stays on
L1 and L4, and vias between them are used in generous parallel arrays, never singly.

Specify 2 oz outer / 1 oz inner explicitly when ordering; the default 4-layer offering at
most fabs is 1 oz outer / 0.5 oz inner and will not carry these currents.

Finish: ENIG. Not for the usual signal-integrity reasons but because the ballast resistor
and output device joints see thermal cycling for years and HASL on wide 2 oz pours gives
an uneven surface for hand-soldering heavy leads.

## 5.2 Trace sizing

Computed from IPC-2221, `A = (I / (k·ΔT^0.44))^(1/0.725)`, with k = 0.048 external and
0.024 internal.

Width in mm for 2 oz external copper:

| Current | ΔT = 10 °C | ΔT = 20 °C |
|---|---|---|
| 1 A | 0.15 | 0.10 |
| 2 A | 0.39 | 0.26 |
| 3 A | 0.68 | 0.45 |
| 5 A | 1.38 | 0.91 |
| 8 A | 2.64 | 1.74 |
| 10 A | 3.60 | 2.36 |
| 12 A | 4.63 | 3.04 |
| 15 A | 6.29 | 4.13 |
| 20 A | 9.36 | 6.14 |
| 25 A | 12.73 | 8.36 |
| 30 A | 16.37 | 10.75 |
| 40 A | 24.34 | 15.98 |

Resistance and drop of 2 oz copper, which is what actually matters for the audio nets:

| Width | Resistance | Per 100 mm | Drop at 10 A |
|---|---|---|---|
| 2 mm | 122.9 mΩ/m | 12.29 mΩ | 123 mV |
| 3 mm | 81.9 mΩ/m | 8.19 mΩ | 82 mV |
| 5 mm | 49.1 mΩ/m | 4.91 mΩ | 49 mV |
| 8 mm | 30.7 mΩ/m | 3.07 mΩ | 31 mV |
| 10 mm | 24.6 mΩ/m | 2.46 mΩ | 25 mV |
| 15 mm | 16.4 mΩ/m | 1.64 mΩ | 16 mV |

The specified widths below are chosen for **voltage drop and inductance**, not thermal
limits — they are all 1.4× to 2× wider than the 10 °C thermal minimum. On a power
amplifier, resistance in the output and ground paths is what degrades damping factor and
what turns ground current into an input-referred error signal.

### Net classes

Apply these as KiCad net classes. Section 6 of `tools/design_calcs.py` prints the same
table, and `NET_CLASSES` in `tools/channel_netlist.py` maps every channel net to its
class.

| Net class | Nets | Peak current | Width | Clearance | Via |
|---|---|---|---|---|---|
| `HV_RAIL_MAIN` | `VCC_MAIN`, `VEE_MAIN` trunk from PSU entry to reservoirs | 25 A | **12.0 mm** | 0.40 mm | 0.8/1.6 mm, ≥8 in parallel |
| `HV_RAIL_CH` | per-channel rail feed from reservoir to output collectors | 10.9 A | **5.0 mm** | 0.40 mm | ≥4 in parallel |
| `SPKR_OUT` | `OUT_STAR`, `SPK_OUT`, ballast resistor nets | 10.9 A | **5.0 mm** | 0.40 mm | ≥4 in parallel |
| `PWR_GND` | output stage returns, reservoirs, Zobel, speaker returns | 25 A | **pour + 12.0 mm min path** | 0.40 mm | array |
| `SIG_GND` | front-end reference | < 100 mA | 0.60 mm | 0.30 mm | 1 |
| `FE_RAIL` | `VCC_FE`, `VEE_FE` | < 200 mA | 0.80 mm | 0.30 mm | 1 |
| `LV_RAIL` | `VCC_15`, `VEE_15` | < 60 mA | 0.60 mm | 0.30 mm | 1 |
| `AUDIO_IN` | `RX`, `TRIM`, `AIN`, `LTP_INP` | signal | 0.35 mm | **0.50 mm** | 1 |
| `FEEDBACK` | `FB`, `OUT_STAR`→R37 tap | signal | 0.40 mm | **0.50 mm** | 1 |
| `BASE_DRIVE` | `PD_N`, `PD_P`, `DR_N`, `DR_P`, output base nets | 500 mA | 0.80 mm | 0.30 mm | 2 |
| `HIZ` | `LC_A`, `BIAS_TOP`, `BIAS_BOT`, `VB_PRE` | signal | 0.40 mm | **0.60 mm** | 1 |
| `SENSE` | `DC_SENSE`, `I_SENSE`, NTC | signal | 0.35 mm | 0.40 mm | 1 |
| `GATE_SMPS` | MOSFET gates (PSU board) | 3 A pulse | 1.50 mm | 0.40 mm | 2 |
| `B_PLUS` | battery input (PSU board) | 30 A cont. | **15.0 mm + busbar** | 1.00 mm | array |
| `SMPS_PWR` | primary switching loop (PSU board) | 45 A peak | **15.0 mm** | 0.60 mm | array |

`HIZ` gets extra clearance because `LC_A` is the highest-impedance node in the amplifier —
it is where a few picoamps of leakage or a few picofarads of stray coupling become
distortion. Keep it short and keep everything away from it.

### Reinforcing the highest-current paths

12 mm of 2 oz copper is 1.64 mΩ per 100 mm. For the rail trunks and `PWR_GND` on the amp
board, and for `B_PLUS` and the primary loop on the PSU board, additionally:

- Leave the copper exposed (no soldermask) along the trunk and flood it with solder, or
- Solder a 2.5 mm² tinned copper bar flat onto the trunk.

Expose these as mask-free rectangles in the layout so the option exists without a
respin. On the PSU board's `B_PLUS` and primary loop, treat the busbar as mandatory, not
optional.

## 5.3 Grounding implementation

The architecture is in `docs/01-system-architecture.md` §1.3. Its physical realisation:

1. **L2 is split.** A `SIG_GND` region covers the front-end area only (see §5.4, regions
   A and B). A `PWR_GND` region covers everything else. The gap between them is 1.5 mm
   and is crossed by **exactly one** copper bridge, 3 mm wide, at the star point.
2. **The star point** is a 15 × 15 mm copper pad on L1/L4 stitched with at least 30 vias,
   located adjacent to the PSU rail entry terminals. It carries: the secondary centre tap
   from the PSU board, the reservoir capacitor returns, all three speaker return
   terminals, the Zobel returns, and the single bridge to `SIG_GND`.
3. **The chassis bond** is a single M4 stud at the star point. Nowhere else does either
   ground touch the chassis.
4. **No signal net crosses the L2 split.** DRC cannot catch this; it must be verified
   visually and by a scripted check (see `docs/07-kicad-automation.md`).
5. **Feedback tap is Kelvin.** `R37` connects to `OUT_STAR` at the exact junction of the
   four ballast resistors, with its own 0.4 mm trace that carries no load current. Tapping
   it anywhere further downstream folds the resistance of that copper into the feedback
   loop and degrades damping factor.
6. **`R38` (feedback lower leg) returns to `SIG_GND`** by the shortest path to the star
   bridge. This single connection sets the amplifier's reference; a millivolt of noise
   here is a millivolt at the input.
7. **Input shield** terminates at the input connector shells through 10 Ω ∥ 100 nF to
   chassis, and the connector shells are isolated from both ground regions.

## 5.4 Amp board placement plan

Board outline: **240 × 160 mm**, rectangular, 3 mm corner radii. Origin at the
bottom-left. Six M3 mounting holes: (10,10), (10,150), (120,10), (120,150), (230,10),
(230,150).

```
        x=0                                                              x=240
 y=160  ┌──────────────────────────────────────────────────────────────────┐
        │  [E] regulators &      │      [D] CH3 MIDBASS device row         │
        │      protection        │      (top heatsink wall)                │
 y=110  │────────────────────────┼─────────────────────────────────────────│
        │  [A]      │  [B]       │   [C] output stages, rails, reservoirs  │
        │  input    │  front-end │       CH3 above, CH1/CH2 below          │
        │  section  │  3 ch      │                                         │
 y=50   │           │            │──────────────────┬──────────────────────│
        │           │            │  [C]             │  [F] PSU entry,      │
        │           │            │                  │      star ground,    │
        │           │            │                  │      speaker terms   │
 y=0    └──────────────────────────────────────────────────────────────────┘
           inputs        [G] CH1 TWEETER  |  CH2 MID device row
           (left edge)       (bottom heatsink wall)
```

| Region | Bounds (mm) | Contents |
|---|---|---|
| A | x 0–40, y 20–110 | input connectors, R1/R2, `INA165x`, shield termination |
| B | x 40–115, y 20–110 | per-channel front-end: LTP, mirror, VAS, servo, trims, ±15 V and ±30 V local decoupling |
| C | x 115–200, y 15–145 | output stages: pre-drivers, base networks, ballast resistors, Zobel, output inductors, rail reservoirs |
| D | x 130–240, y 145–160 | channel 3 device row against the top heatsink wall |
| E | x 0–130, y 110–160 | ±30 V and ±15 V regulators, protection block, relays, indicator LEDs |
| F | x 200–240, y 0–110 | PSU rail entry, star ground pad, chassis stud, speaker terminals |
| G | x 10–240, y 0–15 | channel 1 and channel 2 device rows against the bottom heatsink wall |

Signal flows left to right and never doubles back. The inputs are at the opposite corner
of the chassis from the PSU board, which sits to the right of region F.

### Power device row coordinates

Devices stand vertically with tabs bolted to a vertical heatsink wall. Within each
channel the order is chosen so the NPN and PNP halves are symmetric about the bias
transistor, which sits in the middle where it reads the average of both halves:

`Q12(NPN) · Q13(NPN) · Q10(NPN drv) · Q7(bias) · Q11(PNP drv) · Q14(PNP) · Q15(PNP)`

Package widths: TO-3P 15.9 mm, TO-220 10.2 mm, TO-126N 8.0 mm. Gap 2.5 mm. Each channel
occupies 107 mm.

Channel 1 (tweeter), bottom row, pad row at **y = 8.0 mm**:

| Device | x centre |
|---|---|
| Q112 `NJW0281G` | 22.95 |
| Q113 `NJW0281G` | 41.35 |
| Q110 `MJE15032` | 56.90 |
| Q107 `TTC004B` bias | 68.50 |
| Q111 `MJE15033` | 80.10 |
| Q114 `NJW0302G` | 95.65 |
| Q115 `NJW0302G` | 114.05 |

Channel 2 (midrange), bottom row, **y = 8.0 mm**: identical spacing, all x offset by
**+112.0 mm** (span 127 → 234).

Channel 3 (midbass), top row, pad row at **y = 152.0 mm**, mirrored vertically: identical
spacing, x offset by **+112.0 mm** (span 127 → 234).

Channel 3 is deliberately on the opposite edge and at the far end from the inputs. It
dissipates 29.2 W worst case against 14.6 W for the others, so separating it spreads the
thermal load across both chassis walls instead of concentrating it.

These coordinates must match the drilled and tapped heatsink walls. Generate the drilling
drawing from the same source (see `docs/07-kicad-automation.md`).

### Placement rules for the implementing agent

1. **The output stage loop must be small.** For each channel, the loop
   `VCC_MAIN reservoir → output collector → emitter → ballast → OUT_STAR → PWR_GND →
   reservoir` is the loop that radiates and that carries the distortion-relevant current.
   Keep its enclosed area under 15 cm² per polarity.
2. **Rail reservoirs sit between the two device rows of their channel**, not at the board
   edge. A reservoir 100 mm from the output devices is not a reservoir.
3. **Ballast resistors (`R31`–`R34`) go immediately at the device leads**, and `OUT_STAR`
   is a compact copper region where all four meet — a physical star, not a trace.
4. **`C9` (Cdom) and the `LC_A` node**: place `Q1`, `Q3`, `Q4`, `Q5` and `C9` within a
   20 × 20 mm cluster. This node's stray capacitance directly changes the compensation.
5. **`Q7` (bias) is on the heatsink**, in the device row, between its channel's NPN and
   PNP groups. Its base/collector/emitter traces come back to region C as a tight
   three-wire group — never routed near the output nets.
6. **Zobel `R35`/`C13` at the output node**, returning to `PWR_GND` directly, with the
   shortest possible loop. A long Zobel return makes the network useless at the
   frequencies it exists to control.
7. **Output inductor `L1` after the Zobel**, air core, with its axis **perpendicular** to
   the other two channels' inductors and at least 25 mm from them. Three air-core
   inductors in a row with parallel axes are three coupled transformers and will produce
   measurable interchannel crosstalk.
8. **Input section symmetry**: the three channels' input circuits should be geometrically
   identical, mirrored only where necessary, so that channel-to-channel matching is a
   consequence of the layout rather than of luck.
9. **Trims `RV1`, `RV2` accessible** without removing the board — trim screws facing the
   chassis lid, with access holes.
10. **Keep the protection sense lines (`DC_SENSE`, `I_SENSE`) away from `SPKR_OUT`.**
    Run them on L3 with L2 `PWR_GND` between them and the output copper.

## 5.5 PSU board placement plan

Board outline: **150 × 120 mm**, 4-layer, same stackup.

```
        ┌────────────────────────────────────────────────┐
        │ [1] B+ entry: fuse, ideal diode, TVS, CM choke │
        │ [2] input bulk caps ── [3] MOSFETs ── T1       │
        │                          (tight loop)          │
        │ [4] controller & gate drive (shielded corner)  │
        │ [5] rectifiers ── [6] output chokes ── [7] res │
        │ [8] aux rectifier + regulators                 │
        │ [9] output terminals / busbar to amp board     │
        └────────────────────────────────────────────────┘
```

Rules, in priority order:

1. **Primary switching loop area minimal.** Input capacitor positive terminal →
   transformer centre tap; transformer primary ends → MOSFET drains; MOSFET sources →
   input capacitor negative. Both current paths must be as short and as wide as physically
   possible, with the capacitors physically adjacent to the MOSFETs. This single loop
   determines how much the board radiates and therefore how much of it ends up in the
   audio.
2. **Secondary rectifier loop area minimal** — equally important and more often missed.
   Rectifier → choke → reservoir → secondary centre tap.
3. **Gate loops short**, with each gate resistor at its MOSFET and the driver within
   20 mm. Gate return goes to the MOSFET source, not to the general ground pour.
4. **Controller in its own corner**, referenced to a quiet local ground that connects to
   `SMPS_GND` at one point near the current-sense shunt.
5. **Current-sense shunt in the common source return**, with Kelvin sense traces routed
   as a differential pair to the comparator.
6. **Transformer clearance**: 5 mm keepout around T1 on all layers; no ground pour under
   its core legs (a pour there is a shorted turn in the leakage field).
7. **Sync header at the board edge**, adjacent to the controller.
8. **Thermal**: MOSFETs and rectifiers on a heatsink wall or bonded to the chassis floor
   with the same vertical-mount convention as the amp board.

## 5.6 Thermal and mechanical

### Thermal budget

From `tools/design_calcs.py` §2, with 40 °C in-cabin ambient and a 125 °C junction design
limit:

| Quantity | Value |
|---|---|
| Worst-case dissipation, all 3 channels | 58.4 W |
| Quiescent dissipation, output stage | 13.0 W |
| **Design thermal load per unit** | **71.3 W** |
| Worst single device (midbass) | 7.3 W |
| Junction-to-case rise | 5.1 °C |
| Case-to-sink rise | 1.8 °C |
| **Required sink-to-ambient** | **≤ 1.09 °C/W** |

| Heatsink | Rth | Sink rise | Junction temp |
|---|---|---|---|
| finned chassis, 250 × 175 mm, 30 mm fins | 0.45 °C/W | 32.1 °C | 79.0 °C |
| same with 40 CFM forced air | 0.20 °C/W | 14.3 °C | 61.2 °C |

The 0.45 °C/W chassis gives 2.4× margin on the requirement, and a 79 °C junction at
worst-case continuous sine drive — a condition music never produces. Natural convection
is sufficient; fans are for peace of mind and for installations in sealed enclosures.

Note this assumes all three channels are simultaneously driven to their worst-case
dissipation point (output at 2·Vcc/π), which cannot happen with real programme material.
Realistic continuous dissipation is 20–30 W.

### Mounting

- Output devices, drivers and bias transistors: TO-3P/TO-220/TO-126N tabs bolted to
  vertical chassis walls with M3, 0.6 N·m.
- Insulators: 0.23 mm alumina or `Kapton`-based pads with thermal compound, giving the
  0.25 °C/W case-to-sink assumed above. **Silicone pads alone are roughly 4× worse and
  will invalidate the thermal budget.**
- Bias transistor `Q7` must have the same quality of thermal contact as the output
  devices; it is measuring their temperature.
- NTC bonded to the chassis wall between channel 3's output devices.

### Chassis

| Item | Spec |
|---|---|
| Outline | ~300 × 200 × 65 mm per unit |
| Construction | extruded aluminium with integral fins on both long walls |
| Wall thickness | ≥ 8 mm where devices bolt |
| Internal partition | 2 mm aluminium between amp board and PSU board, bonded to chassis |
| Board mounting | M3 standoffs, 10 mm, boards parallel to the floor |
| Terminals | inputs on one end face, speaker and power on the other |
| Ground stud | single M4 at the amp board star point |

### Electrical system requirements

Both units together draw about 40 A continuous at full output.

| Item | Spec |
|---|---|
| Main feed | 4 AWG minimum (2 AWG preferred for long runs) |
| Main fuse | 60–80 A at the battery, within 300 mm |
| Per-unit fuse | 30 A on each PSU board |
| Ground | 4 AWG to chassis, same gauge as positive, short as possible |
| Alternator/battery grounds | upgraded ("big three") |

Undersized wiring will limit output long before the amplifiers do, and the voltage drop
shows up as the converters running at higher duty cycle and lower efficiency.

## 5.7 Design rule checks

Beyond standard DRC, these need scripted or visual verification:

| Check | Method |
|---|---|
| No signal net crosses the L2 ground split | scripted: intersect signal-net geometry with the split polygon |
| Exactly one bridge between `SIG_GND` and `PWR_GND` | scripted: count copper connections |
| `SIG_GND` carries no load current | topological review of the netlist |
| Feedback tap is at the ballast junction | scripted: check `R37` pad distance to `OUT_STAR` centroid |
| Output loop area under 15 cm² | scripted polygon area per channel |
| Rail trunk width ≥ 12 mm everywhere | KiCad net class DRC |
| Air-core inductor axes non-parallel and ≥ 25 mm apart | placement review |
| Device row x coordinates match the heatsink drawing | scripted comparison against the drill table |
| No pour under T1 core legs | keepout DRC |
| Creepage on `B_PLUS` and rails ≥ 1.0 mm | DRC clearance class |
