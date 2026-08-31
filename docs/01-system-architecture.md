# 01 — System Architecture

## 1.1 What is being built

Two identical units. Each unit is one side of the front stage and contains two PCBs in
one chassis:

- **AMP board** — three discrete Class-AB channels, the front-end regulators, and the
  protection/control logic.
- **PSU board** — one regulated push-pull DC-DC converter producing all rails.

Splitting left and right into separate units with separate supplies, separate ground
returns and separate chassis removes the single largest source of degraded stereo
separation in car audio: shared supply impedance. Crosstalk between the two sides is
then limited only by the source (the DSP) and the cabling.

```
                            ┌──────────────── UNIT (×2, one per side) ─────────────────┐
                            │                                                          │
 Battery ──┬── 60–80 A ──┬──┼──► 30 A fuse ──► PSU BOARD                               │
           │   fuse      │  │                  ┌──────────────────────────────────┐    │
           │             │  │                  │ ideal-diode reverse protection   │    │
 DSP ──────┼─────────────┼──┼──► balanced in   │ CM choke + bulk input filter     │    │
   3 ch    │             │  │    (3 pairs)     │ SG3525A push-pull, 65 kHz        │    │
   per     │             │  │                  │ 2×2 IRFB4110 → ETD44 transformer │    │
   side    │             │  │  SYNC ◄──────────┤ choke-input LC output filters    │    │
           │             │  │  (to other unit) │ regulated, direct feedback       │    │
           │             │  │                  └───────┬──────────┬───────────────┘    │
           │             │  │                          │ ±24 V    │ ±33 V raw          │
           │             │  │                  ┌───────▼──────────▼───────────────┐    │
           │             │  │                  │ AMP BOARD                        │    │
           │             │  │                  │  ±30 V and ±15 V linear regs     │    │
           │             │  │                  │                                  │    │
           │             │  │   IN_T ─────────►│  ch1  tweeter  4 Ω  ──► relay ───┼──► tweeter
           │             │  │   IN_M ─────────►│  ch2  mid      4 Ω  ──► relay ───┼──► mid
           │             │  │   IN_B ─────────►│  ch3  midbass  2 Ω  ──► relay ───┼──► midbass
           │             │  │   REM ──────────►│  protection + sequencing         │    │
           └─────────────┴──┼──────────────────┴──────────────────────────────────┘    │
                            └──────────────────────────────────────────────────────────┘
```

## 1.2 Rail plan

Four regulated rails. Regulation is the point: an unregulated car supply moves the rails
with battery voltage and with the bass, which modulates the output stage and is audible.

| Rail | Voltage | Source | Load | Purpose |
|---|---|---|---|---|
| `VCC_MAIN` / `VEE_MAIN` | ±24 V ±2 % | SMPS, choke-input filtered | output stages, ~5.2 A/rail avg at full power | delivers the audio power |
| `VCC_FE` / `VEE_FE` | ±30 V | aux winding → `LM317HV`/`LM337HV` | LTP, VAS, pre-drivers, ~50 mA | lets the output stage swing to within 2.2 V of the main rail, and isolates the front-end from output-stage rail modulation |
| `VCC_15` / `VEE_15` | ±15 V | ±30 V → `LM317`/`LM337` | line receivers, DC servos, ~40 mA | clean low-noise rails for the small-signal ICs |
| `V_BATT` | 11–15 V | battery, fused | relay coils, protection logic | keeps relay coil transients out of the audio rails entirely |

The ±30 V front-end rail is what makes the "50 W" target comfortable rather than
marginal. Without it the VAS clips before the output stage and you lose roughly 1 dB of
output plus a burst of odd-order distortion right at the clipping threshold.

### Rail sizing rationale

Because the ±24 V rails are actively regulated with a loop bandwidth of a few kHz, the
reservoir capacitance only has to cover the converter's response time, not a full bass
half-cycle. At 10.9 A and a 50 µs loop response, 545 µF holds droop to 1 V, so the
specified 4700 µF per rail on each board is roughly 8× margin. This is why a regulated
supply needs a fraction of the capacitor bank of an unregulated one.

## 1.3 Grounding architecture

This is the part that decides whether the amplifier measures well or hums. Three
separate ground domains, joined at exactly one point.

```
   SIG_GND ─────┐  front-end reference: line receivers, DC servos, gain trim,
   (quiet)      │  LTP tail reference, feedback network bottom (Rg)
                │
   PWR_GND ─────┼──► STAR ──► chassis stud ──► single 4 AWG return to battery negative
   (dirty)      │  output stage emitter returns, Zobel networks, rail reservoirs,
                │  speaker return terminals
                │
   SMPS_GND ────┘  converter input filter, MOSFET sources, transformer secondary
   (filthy)        centre tap, output rectifier returns
```

Rules that follow from this, and which the layout must enforce:

1. **`SIG_GND` carries no load current.** It connects to the star point through one
   short link and nothing else. Any speaker or supply current that finds its way into
   `SIG_GND` appears directly at the amplifier input multiplied by the closed-loop gain.
2. **The feedback network bottom (`Rg`) references `SIG_GND`,** and the feedback top
   taps the output at the junction of the emitter ballast resistors — a Kelvin tap ahead
   of the output inductor and ahead of any high-current trace.
3. **Speaker returns come back to the star point,** never to the chassis at the speaker
   end and never to a local ground pour.
4. **The transformer secondary centre tap is the origin of the ±24 V return** and bonds
   to the star point through the shortest, widest possible path.
5. **The transformer gets an interwinding copper shield** bonded to `SMPS_GND`. Without
   it, primary switching edges couple straight into the audio reference through
   interwinding capacitance, which is the usual cause of the faint 65 kHz hash you can
   see on a scope at the speaker terminals of cheap amplifiers.
6. **Input shields terminate at the chassis entry** through 10 Ω in parallel with 100 nF,
   not directly to `SIG_GND`. This drains RF without creating a ground loop with the DSP.

Because the amplifier's ±24 V return and the battery negative are common through the
chassis anyway, the converter does **not** need galvanic isolation. This is exploited:
the regulation feedback is direct-coupled instead of going through an optocoupler, which
gives a faster, more predictable control loop and removes the optocoupler's drift and
ageing from the rail accuracy.

## 1.4 Gain and level plan

| Point | Level |
|---|---|
| DSP output (assumed) | 2–8 V RMS, balanced |
| Line receiver output | same, unity gain, 91 dB CMRR |
| After gain trim | 0.10–0.77 V RMS, set at install |
| Power stage gain | 20.1 V/V fixed (26.1 dB); 19.85 V/V simulated |
| Output at clipping | 15.8 V RMS (22.3 V peak) into 4 Ω, 15.1 V RMS (21.3 V peak) into 2 Ω |

The clipping level depends on load because the ceiling is the rail minus the emitter
ballast drop minus `Vce(sat)`, and the 2 Ω channel draws twice the current through the
same ballast. See docs/02 §2.3 for the measured table.

Input sensitivity for clipping is 0.766 V RMS at the power stage. The trim range covers
DSP outputs from roughly 0.8 V to 8 V RMS. Setting the trim so the amplifier clips just
above the DSP's clipping point wastes no dynamic range and keeps the noise floor as low
as the design allows.

Gain is deliberately low. Every dB of gain you don't use is a dB of noise you don't
amplify, and with a DSP upstream there is no reason to run a car amplifier at the 30+ dB
gain typical of head-unit-driven designs.

## 1.5 Signal path inventory

What the audio actually passes through, in order, and nothing else:

1. 100 Ω 0.1 % thin-film series resistor (RF/ESD)
2. `INA1650`/`INA1651` balanced line receiver, unity gain
3. 2.2 kΩ thin film + 10 kΩ cermet trim (attenuator)
4. 2.2 µF polypropylene/polyester film coupling capacitor
5. 1 kΩ thin-film base stopper
6. Discrete power amplifier: PNP LTP → NPN current mirror → beta-enhanced NPN VAS →
   EF3 output triple
7. 0.22 Ω emitter ballast resistors
8. 2.2 µH air-core output inductor
9. Relay contact
10. Speaker terminal

There are **no electrolytic capacitors in the signal path and none in the feedback
loop**. The usual large electrolytic across the feedback lower leg is replaced by a DC
servo using a film capacitor, which removes both its distortion and its
low-frequency phase shift. There are no crossover filters, no tone controls, no bass
boost and no muting FET in series with the signal.

## 1.6 Design decision log

Recording the reasoning so a later change can be evaluated rather than guessed at.

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Output topology | discrete Class AB | Class D | no switching residue, no output filter interacting with the load, no dead-time distortion; the thermal cost (71 W/unit worst case) is manageable in a chassis heatsink |
| Output stage | EF3 triple, 2 pairs/channel | EF2 double, 1 pair | the triple isolates the VAS from the load so the VAS sees a constant, light load; two pairs halve device current, which keeps hFE in its linear region and roughly halves large-signal distortion at 2 Ω |
| Bias tracking | Vbe multiplier on the heatsink | ThermalTrak devices | ThermalTrak is discontinued |
| Input stage | PNP LTP, degenerated 220 Ω, current-mirror load | single-ended, or op-amp front end | balanced LTP with a mirror gives high loop gain and low distortion; degeneration linearises the stage and sets the compensation cleanly |
| DC handling | DC servo, film capacitor | electrolytic in the feedback leg, or input coupling only | removes the last electrolytic from the loop |
| Rails | regulated ±24 V | unregulated tracking the battery | rails that move with the battery and with the bass modulate the output stage; regulation also fixes the maximum output power regardless of alternator state |
| Front-end supply | separate regulated ±30 V | share the ±24 V main rail | full output swing plus high PSRR at the most sensitive nodes |
| Converter | push-pull, `SG3525A`, voltage mode | `UCC2808A` current mode | the `SG3525A` sync pin phase-locks the two units, which eliminates beat products between the left and right converters; peak current limit is added externally through the shutdown pin |
| Converter isolation | non-isolated, direct feedback | optocoupler feedback | audio ground and battery negative are already common; direct feedback is faster and more stable |
| Output filtering | choke-input LC | capacitor-input | choke-input makes duty-cycle regulation actually work, and drastically lowers capacitor ripple current |
| Board split | two boards, side by side, shielded | one board, or stacked | keeps 20 A switching loops physically away from millivolt-level inputs |
| Crossovers | none | on-board active filters | you have a DSP; every filter stage on the board would be a stage the signal doesn't need |
| Muting | output relay only | series FET or JFET shunt | nothing in series with the signal; the relay is already required for DC fault protection |

## 1.7 What this design assumes you have

- An upstream DSP providing three filtered, time-aligned, level-matched channels per
  side, preferably with balanced or floating outputs.
- Electrical system capable of roughly 40 A continuous for both units: 4 AWG (or larger)
  power and ground runs, a 60–80 A main fuse at the battery, and the alternator/battery
  grounds upgraded. Undersized wiring will limit output long before the amplifiers do.
- Enough mounting area for two chassis of roughly 300 × 200 × 65 mm with airflow.
