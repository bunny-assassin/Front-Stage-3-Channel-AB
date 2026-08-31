# 03 — PSU Board: Regulated Push-Pull Converter

One board per unit. Converts 11–15 V battery to regulated ±24 V plus an auxiliary
winding for the front-end rails. Rated 250 W continuous, 350 W for 10 s.

This is the highest-risk part of the project. It handles 27 A of input current, and a
wiring or phasing mistake destroys MOSFETs instantly. Build and validate it standalone,
into a resistive load, before it ever connects to the amplifier board.

## 3.1 Why push-pull, regulated, non-isolated

**Push-pull** because at 12 V input the primary current is high and a centre-tapped
primary with two ground-referenced switches avoids high-side gate drive entirely.

**Regulated** because unregulated car amplifier rails follow the battery — rails sag on
bass transients and change with alternator state, which modulates the output stage and
changes maximum power depending on whether the engine is running. Regulation also means
the reservoir capacitance only has to cover the control loop's response time rather than
a bass half-cycle: 545 µF suffices for 1 V droop at 10.9 A, so the specified 4700 µF per
rail is generous.

**Non-isolated** because audio ground and battery negative are already common through
the chassis. Exploiting this lets the regulation feedback be direct-coupled instead of
routed through an optocoupler, which gives a faster and more predictable loop and
removes optocoupler drift from rail accuracy. The transformer still needs an
interwinding shield — see §3.6.

**Choke-input output filter** because with a capacitor-input filter the output tracks the
peak of the secondary square wave regardless of duty cycle, so duty-cycle regulation
barely works. Choke-input makes the converter behave like a buck stage, where
Vout = 2·Vin·(Ns/Np)·D, and duty-cycle control regulates properly. It also drops
capacitor ripple current dramatically, which is why the reservoirs will still be healthy
in ten years.

## 3.2 Operating point

| Parameter | Value | Source |
|---|---|---|
| Switching frequency | 65 kHz | chosen: harmonics of 65 kHz land clear of the AM broadcast band, and it is low enough that a 3-turn primary and Schottky rectifiers stay efficient |
| Period | 15.38 µs | — |
| Duty cycle, per switch | 0.332 at 14.4 V / 0.379 at 12.6 V / 0.435 at 11.0 V | calculated |
| Max duty limit | 0.45 | set by dead-time resistor |
| Input current at 250 W | 20.4 A at 14.4 V / 26.7 A at 11.0 V | at 85 % efficiency |
| Rail current at full power | 5.2 A per rail | — |
| MOSFET Vds stress | 30 V plus leakage ringing | 2 × Vin |
| Primary RMS current | ~16.5 A per switch | — |

The 0.435 duty figure at 11 V is the design corner. It leaves headroom below the 0.45
limit, so the rails hold regulation during cranking rather than collapsing — which is
what produces the characteristic "amplifier mutes when you start the car" behaviour.

## 3.3 Transformer T1

**Core:** ETD44, 3C95 or N87 ferrite, ungapped. Effective area 173 mm².

Flux swing at the 15 V worst case with a 3-turn primary half is 0.222 T peak-to-peak,
against roughly 0.4 T saturation at 100 °C — about 1.8× margin, which is the right place
to be for a voltage-mode push-pull where flux walking is a real failure mode.

| Winding | Turns | Conductor | Notes |
|---|---|---|---|
| Primary | 3 + 3 (centre-tapped) | 0.25 mm × 25 mm copper foil per half | foil is strongly preferred over wire: at 65 kHz the skin depth is 0.26 mm, and foil also gives the tight coupling that keeps the leakage spike small |
| Shield | 1 turn, not shorted | 0.1 mm copper foil, one end only to `SMPS_GND` | between primary and secondary |
| Main secondary | 8 + 8 (centre-tapped) | 8 strands of 0.5 mm enamelled, twisted | 5.2 A RMS per half |
| Aux secondary | 11 + 11 (centre-tapped) | 0.4 mm single | supplies the ±30 V front-end regulators |

Winding order, innermost first: primary half A, shield, main secondary, aux secondary,
primary half B. Interleaving the primary halves around the secondary halves the leakage
inductance and improves the coupling symmetry between the two primary halves, which is
what keeps flux walking under control.

**Verify window fill before committing.** If the ETD44 window will not take these
windings comfortably, move to ETD49 and keep the turns counts — the flux margin only
improves. Do not reduce the conductor cross-sections to fit.

**Phasing is critical and is the most common build failure.** Mark the start of every
winding. The two primary halves must drive the core in opposite senses; the two
secondary halves must rectify into the same polarity. Verify with a low-voltage signal
generator and a scope on the bench before applying battery power.

## 3.4 Circuit blocks

### Input protection and filtering

| Block | Implementation |
|---|---|
| Fuse | 30 A ATO blade fuse holder, board-mounted |
| Reverse polarity | `LM74700-Q1` ideal-diode controller driving an `IRFB4110` in the B+ line. A Schottky would dissipate 12 W at 25 A; this dissipates about 2 W. |
| Transient protection | bidirectional TVS rated for automotive load dump, 30 V standoff class, plus a 33 V unidirectional clamp across B+ |
| Common-mode choke | 2 × 15 turns of 1.5 mm² on a ferrite toroid, ~25 µH per winding — keeps converter switching noise off the battery wiring, which otherwise radiates into every other device in the car |
| Bulk input | 2 × 4700 µF 25 V low-ESR + 2 × 1 µF film + 4 × 100 nF ceramic distributed at the MOSFET drains |
| Soft start | `SG3525A` internal soft-start with a 10 µF capacitor, giving roughly 1 s ramp |

### Controller and gate drive

| Ref | Part | Notes |
|---|---|---|
| U10 | `SG3525A` | voltage-mode push-pull PWM, DIP-16 or SOIC-16 |
| U11 | `UCC27524A` | dual 5 A gate driver — the `SG3525A`'s own 400 mA outputs are too slow for four paralleled `IRFB4110` |
| Q20–Q23 | `IRFB4110` ×4 (2 per side) | 100 V, 3.7 mΩ, TO-220 |
| R gate | 4.7 Ω per MOSFET, individual | individual resistors, never a shared one, or the paralleled devices will fight |
| Snubber | 10 Ω + 2.2 nF 100 V C0G across each drain to `SMPS_GND` | tune the resistor at bring-up while watching the drain waveform |

`SG3525A` configuration:

- **Frequency:** Rt/Ct for 65 kHz. Set Ct = 10 nF and trim Rt to land on frequency;
  measure, do not trust the nominal formula.
- **Dead time:** resistor between `CT` and `DISCHARGE` set for roughly 400 ns. Dead time
  is mandatory — any overlap shorts the primary through both switches.
- **Sync:** pin brought out to a 2-pin header, `SYNC` and `SMPS_GND`. **Wire the two
  units' sync pins together with a short shielded pair.** Without this, the two
  converters run at slightly different frequencies and their difference frequency can
  land in the audio band as a wandering tone. This is the single highest-value detail on
  this board and costs one connector.
- **Shutdown:** pin 10, driven by the protection latch and by the overcurrent comparator.
- **Soft start:** 10 µF.

### Output rectification and filtering

| Block | Implementation |
|---|---|
| Rectifiers | one dual Schottky per rail, 100 V / 30 A, TO-247 (e.g. `MBRB30H100CT` class). Peak reverse voltage is about 2 × 26 V plus ringing, so 100 V is the right rating. |
| Snubbers | 10 Ω + 2.2 nF across each rectifier |
| Output choke | coupled inductor, 33 µH per winding, 10 A saturation, bifilar on a sendust or Kool Mµ toroid. Coupling the two rails on one core keeps them tracking. |
| Reservoir | 4700 µF 35 V low-ESR per rail + 1 µF film + 100 nF ceramic per rail |
| Second stage | 4.7 µH + 1000 µF per rail before the board-to-board connector, to attenuate residual switching ripple |

### Regulation loop

Feedback is direct-coupled and senses the **sum** of the two rails, so the loop regulates
total secondary volts and both rails stay balanced:

- R from `VCC_MAIN` and an equal R from `VEE_MAIN` into a summing node, with the divider
  scaled to present 5.1 V to the `SG3525A` error amplifier inverting input against its
  internal reference.
- Type-2 compensation on the error amplifier output: series R + C to ground, target
  crossover about 3–5 kHz with 50° phase margin. Choke-input output makes this a
  well-behaved two-pole plant.
- Sensing the sum rather than one rail avoids the case where one rail is loaded and the
  other drifts up.

### Overcurrent limit

A shunt in the common source return (0.005 Ω, four-terminal or a copper trace of
calculated resistance) feeds a comparator that pulls `SG3525A` pin 10 on a pulse-by-pulse
basis. Trip at roughly 45 A of primary current. This is what covers flux imbalance in a
voltage-mode push-pull — the condition where one half-cycle saturates the core and the
switch current runs away within a few cycles.

### Auxiliary rails

**The aux winding must be choke-input, not capacitor-input.** With duty-cycle regulation,
only a choke-input output is actually regulated — a capacitor-input winding follows the
peak of the secondary square wave, which here would swing from 40 V at 11 V input to 53 V
at 14.4 V input and would force 60 V regulators with several watts of dissipation.

With a choke-input filter the aux rail is regulated by the same duty cycle as the main
output, and simply scales with the turns ratio:

    V_aux = V_secondary × (N_aux / N_sec) = 25.5 V × 11/8 = 35.1 V

| Stage | Implementation | Dissipation |
|---|---|---|
| Rectify | 2 × `MURS120` ultrafast | — |
| Choke | 2.2 mH, 100 mA, one per rail | — |
| Preload | 2.2 kΩ per rail (16 mA) | keeps the choke in continuous conduction at light load |
| Reservoir | 220 µF 63 V + 1 µF film per rail | — |
| Regulate to ±30 V | `LM317T` / `LM337T` | 0.25 W each |
| Regulate to ±15 V | `LM317T` / `LM337T` from the ±30 V rails | 0.6 W each |

Continuous conduction check at 14.4 V input: the ripple current in a 2.2 mH choke is
about 41 mA peak-to-peak, so conduction stays continuous above roughly 20 mA of load. The
front-end draws about 50 mA, and the 2.2 kΩ preload guarantees the condition at idle. If
the choke ever goes discontinuous the aux rail rises toward 53 V and the regulators exceed
their 40 V rating — hence the preload.

If you want the lowest possible noise on the line-receiver rails, `TPS7A4700` (positive)
and `TPS7A3301` (negative) replace the ±15 V regulators, fed from the ±30 V rails, and are
roughly 20 dB quieter. A drop-in improvement, not a requirement.

## 3.5 Board-to-board interface

| Signal | Conductor |
|---|---|
| `VCC_MAIN`, `VEE_MAIN` | 2.5 mm² each, or bolted busbar, 60 mm maximum length |
| Secondary centre tap (`PWR_GND`) | 4 mm², shortest possible, straight to the amp board star point |
| `VCC_FE_RAW`, `VEE_FE_RAW` | 0.5 mm² |
| `SHUTDOWN` | 0.5 mm², from the amp board protection latch |
| `SYNC` | shielded pair to the other unit |

Use screw terminals or bolted lugs for the power rails, not pin headers. A 10 A
connector contact resistance of 20 mΩ is 0.2 V of loss and a slowly degrading joint.

## 3.6 Noise control requirements

The whole point of separating the boards is undone by careless coupling:

1. **Interwinding shield in T1**, grounded at one end only to `SMPS_GND`. Without it,
   primary switching edges couple into the audio reference through interwinding
   capacitance. This is the usual source of the low-level 65 kHz hash visible at the
   speaker terminals of cheap amplifiers.
2. **Aluminium shield partition** between the PSU board and the amp board, bonded to the
   chassis.
3. **Keep the primary switching loop tiny** — input capacitor, transformer centre tap,
   MOSFET drains and sources. This loop area determines how much magnetic field the board
   radiates.
4. **The secondary rectifier loop is equally important** and is more often neglected.
5. **No audio signal routing anywhere near the PSU board.** Inputs enter the chassis at
   the opposite end.
6. **Sync the two units.** Repeated because it is easy to skip and hard to diagnose later.

## 3.7 PSU bring-up gates

Never connect this to the amplifier board until all of these pass. Full procedure in
`docs/06-bringup-and-test.md`.

1. Controller alone on a bench supply: verify 65 kHz, 400 ns dead time, and that the two
   gate outputs are 180° out of phase. In-phase outputs are the classic failure and they
   destroy the primary.
2. Transformer phasing verified with a signal generator, MOSFETs not installed.
3. First power-up at 6 V input through a 5 A current-limited supply, into a light load.
4. Ramp to 12 V with resistive load, verify regulation, then check the drain waveform and
   tune the snubber.
5. Full 250 W into resistive load for 30 minutes, thermal imaging or thermocouples on the
   transformer, MOSFETs and rectifiers.
6. Verify overcurrent trip with a deliberate overload.
7. Verify cranking behaviour by sweeping the input from 15 V down to 10 V under load.
