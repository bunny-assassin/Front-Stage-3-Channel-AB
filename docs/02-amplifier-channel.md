# 02 — Amplifier Channel Design

One hierarchical sheet, `AMP_CHANNEL`, instantiated three times per board. All three
instances are electrically identical; only the load differs (4 Ω, 4 Ω, 2 Ω). Making the
channels identical means one channel gets simulated, laid out and validated, and the
result is reused with confidence.

Reference designators below are sheet-local. After hierarchical annotation they become
`R101…` (tweeter), `R201…` (midrange), `R301…` (midbass).

## 2.1 Topology

A three-stage voltage-feedback amplifier, which is the topology with the lowest
achievable distortion floor when each stage's known weakness is addressed
individually.

```
 IN+ ──R1──┐
           │  ┌──────────┐        ┌────────┐    ┌─────────────────────────────────┐
 IN- ──R2──┴──┤ INA165x  ├──R3────┤ RV1    ├────┤ PNP LTP, 220R degenerated       │
              │ balanced │        │ 10k    │    │ tail 4 mA from LED-ref'd CCS    │
              │ receiver │        │ trim   │    │            │                    │
              │ unity, ±15V       └────────┘    │            ▼                    │
              └──────────┘                      │ NPN current-mirror load, 68R    │
                                                │            │                    │
                                                │            ▼  LC_A (high-Z)     │
                                                │ beta-enhanced NPN VAS, 10 mA    │
                                                │ TTC004B, 100R degeneration      │
                                                │ Cdom 68 pF Miller               │
                                                │            │                    │
                                                │            ▼  VAS collector     │
                                                │ Vbe multiplier bias spreader    │
                                                │ (TTC004B bolted to heatsink)    │
                                                │            │                    │
                                                │            ▼                    │
                                                │ EF3 output triple:              │
                                                │   pre-driver  TTC004B / TTA004B │
                                                │   driver      MJE15032 / 15033  │
                                                │   output   2× NJW0281G / 0302G  │
                                                │   ballast  4× 0R22 3W           │
                                                └──────┬──────────────────────────┘
                                                       │ OUT_STAR
                                    ┌──────────────────┼─────────────┬────────────┐
                                    │                  │             │            │
                              R37 2k2 ──► FB      Zobel R35/C13   L1 2u2 ║ R36   DC servo
                              R38 115R to SIG_GND                      │        (OPA1642)
                                                                       ▼
                                                                  relay ──► SPEAKER
```

### Why each stage is built the way it is

**Input stage — PNP long-tailed pair, 220 Ω degeneration, current-mirror load.**
The mirror forces the two collector currents equal, which balances the pair and roughly
halves second-harmonic distortion compared to resistive loading. Degeneration linearises
the transconductance and, more usefully, *sets* it — 2.146 mS — which makes the
compensation a calculation rather than a guess. The tail current source is referenced to
a red LED rather than a resistor divider or zener: LEDs have far lower noise than zeners
and a convenient ~1.8 V drop.

**VAS — beta-enhanced NPN with a current-source load.** The beta enhancer (an emitter
follower ahead of the VAS base) raises the impedance the mirror output node sees, which
preserves the loop gain the input stage worked to produce. The current-source load
instead of a bootstrap gives a genuinely constant, high impedance down to DC. 100 Ω
emitter degeneration applies local feedback around the VAS, linearising the stage that
otherwise dominates distortion at high frequency.

**Output stage — EF3 (triple).** This is the single most important choice for 2 Ω
capability. In a two-stage (EF2) output the VAS has to supply the driver base current,
which at 10.9 A peak into 2 Ω becomes a large, signal-dependent load on the most
sensitive high-impedance node in the amplifier. The triple isolates the VAS almost
completely: it sees a few milliamps that barely vary. Two output pairs then halve the
per-device current to 5.45 A peak, keeping hFE in its flat region and cutting
large-signal distortion roughly in half again.

**Bias — Vbe multiplier on the heatsink.** With ThermalTrak discontinued, the multiplier
transistor `Q7` bolts to the heatsink between the output devices of its own channel and
tracks their case temperature. It over-compensates slightly at first (the junction heats
faster than the case), which is the safe direction.

## 2.2 Component values

### Input receiver and gain trim

| Ref | Value | Notes |
|---|---|---|
| R1, R2 | 100 Ω 0.1 % thin film | series RF/ESD; matching matters, 20 Ω mismatch costs 7 dB of CMRR |
| U1 | `INA1650IPW` (ch1+ch2) / `INA1651IPW` (ch3) | TSSOP-14 both — same footprint, so all three channel blocks lay out identically |
| R3 | 2.2 kΩ 0.1 % thin film | sets the top of the attenuator |
| RV1 | 10 kΩ cermet trimmer, 25-turn | gain trim, set once at install |
| C6 | 0 Ω link fitted by default | film-cap coupling option, see §2.4 |
| R4 | 100 kΩ | defines `AIN` if the receiver is removed |
| R6 | 1 kΩ 0.1 % | base stopper / RF filter with C7 |
| C7 | 220 pF | input pole; 723 kHz against R6 alone, but 207 kHz once the trimmer wiper is included — see below |

The input pole is worth stating properly because the obvious calculation is wrong.
R6·C7 gives 723 kHz, but C7 sees R6 *plus* whatever the trimmer wiper looks like,
and a 10 kΩ pot used as a divider presents up to 2.5 kΩ at mid-travel. The real
pole therefore runs from 723 kHz with the trimmer at maximum down to 207 kHz at
mid-travel, so the channel's small-signal bandwidth depends slightly on where the
gain is set.

This is deliberately left alone rather than "fixed". The consequence at 20 kHz is
between 1.6° and 5.5° of phase lag, so two channels trimmed differently can differ
by about 4° at 20 kHz — which sounds alarming until you notice that in a 3-way
active system only the tweeter channel is passing 20 kHz at all. At the crossover
frequencies where inter-channel phase actually matters, 300 Hz and 3 kHz, the
spread is 0.08° and 0.8°. The alternatives all cost something real: raising R6
raises both input noise and the base-current offset the servo has to absorb, and
shrinking the pot means rescaling the whole gain plan. A 207 kHz worst case is
also the better RF filter, which in a car is not nothing.

`U1` runs on ±15 V with `REF` and `COM` tied to `SIG_GND`, which is the connection that
achieves the full 91 dB CMRR (tying them to `VMID(OUT)` instead costs 5 dB).
`VMID(IN)` gets a 1 µF capacitor to `SIG_GND` to keep the internal divider quiet.
Provide a DNP 1 MΩ footprint from `COM` to `SIG_GND`; the datasheet describes this as
mitigating CMRR loss under large source-impedance mismatch, and the implementing agent
should confirm the exact recommended connection against datasheet §8 before populating.

### Input stage and VAS

| Ref | Part / value | Function | Operating point |
|---|---|---|---|
| Q1 | `BCM857BS` dual PNP, SOT-363 | input LTP, monolithically matched and thermally coupled | 2.0 mA per side |
| R8, R9 | 220 Ω 0.1 % | LTP emitter degeneration | 0.44 V across each |
| Q2 | `BC857C` PNP | tail current sink | 4.0 mA |
| R10 | 287 Ω 0.1 % | sets tail current | 1.15 V across |
| D1 | red LED, 2 mm | tail voltage reference, ~1.8 V | 1.88 mA |
| R11 | 15 kΩ | LED bias | — |
| C8 | 100 nF | decouples `TREF` to `VCC_FE` | — |
| Q3 | `BCM847BS` dual NPN, SOT-363 | current-mirror load | 2.0 mA per side |
| R12, R13 | 68 Ω 0.1 % | mirror emitter degeneration | 136 mV across each |
| Q4 | `BC847C` NPN | VAS beta enhancer | ~215 µA |
| R14 | 10 kΩ | keeps Q4 conducting | 165 µA |
| R18 | 100 Ω | Q5 base stopper | — |
| Q5 | `TTC004B` NPN, TO-126N | VAS, 160 V, Cob 12 pF | 10 mA, Vce up to 58 V |
| R15 | 100 Ω | VAS emitter degeneration | 1.0 V across |
| C9 | 68 pF, C0G | dominant-pole Miller capacitor | — |
| R16 + C10 | 1 kΩ + 1 nF, **DNP** | two-pole compensation option | — |
| Q6 | `TTA004B` PNP, TO-126N | VAS current-source load | 10 mA, 0.58 W worst case |
| R19 | 115 Ω 0.1 % | sets VAS current | 1.15 V across |
| D2 | red LED, 2 mm | current-source reference | 1.88 mA |
| R20 | 15 kΩ | LED bias | — |
| C11 | 100 nF | decouples `CSREF` | — |

Verified DC operating points, front-end on ±30 V rails: `TREF` = +28.2 V, Q2 emitter
= +28.85 V, mirror bases = −29.2 V, Q5 base = −28.35 V, `LC_A` = −27.7 V. The mirror
transistor `Q3A` therefore sits at 2.16 V collector-emitter — comfortably out of
saturation, which is the operating point most easily got wrong in this topology.

### Bias spreader

| Ref | Part / value | Notes |
|---|---|---|
| Q7 | `TTC004B` NPN, TO-126N | **bolted to the heatsink between this channel's output devices** |
| R21 | 3.3 kΩ | multiplier upper leg |
| RV2 | 1 kΩ cermet trimmer, 25-turn | bias adjust |
| R22 | 220 Ω | limits minimum spread — without it, a trimmer at zero would command runaway bias |
| C12 | 100 nF | keeps the spreader low-impedance at HF |
| D3 | 5.1 V zener, `BZX84C5V1` | **failsafe.** If Q7 fails open, the 10 mA VAS current would otherwise drive the full divider drop into the output stage and destroy it. The zener caps the spread at 5.1 V, limiting quiescent current to roughly 1.7 A per device — survivable long enough for the bias-runaway detector to latch. |

Target spread is 3.92 V: six base-emitter drops at 45 mA per device plus 2 × 9.9 mV
across the ballast resistors. With Vbe = 0.62 V the multiplier needs a ratio of 6.32, so
the lower leg lands at 620 Ω — mid-travel on the trimmer, which is where you want it.
Trimmer range gives a spread of 3.7 V to 16 V; the zener is what makes that upper end
non-destructive.

### Output stage

| Ref | Part / value | Notes |
|---|---|---|
| Q8 | `TTC004B` NPN, TO-126N | NPN pre-driver, collector to `VCC_FE` |
| Q9 | `TTA004B` PNP, TO-126N | PNP pre-driver, collector to `VEE_FE` |
| R23, R24 | 2.2 kΩ | pre-driver emitter loads to `OUT_STAR`, ~1 mA idle |
| Q10 | `MJE15032` NPN, TO-220 | driver, **on the heatsink** |
| Q11 | `MJE15033` PNP, TO-220 | driver, **on the heatsink** |
| R25, R26 | 220 Ω | driver emitter loads to `OUT_STAR`, ~6 mA idle |
| Q12, Q13 | `NJW0281G` NPN, TO-3P | outputs, **on the heatsink** |
| Q14, Q15 | `NJW0302G` PNP, TO-3P | outputs, **on the heatsink** |
| R27–R30 | 4.7 Ω 0.5 W | output base stoppers — mandatory, these suppress local VHF oscillation in paralleled devices |
| R31–R34 | 0.22 Ω 3 W non-inductive | emitter ballast; forces current sharing between the two pairs and adds local degeneration |
| R35 | 10 Ω 3 W | Zobel |
| C13 | 100 nF 100 V film | Zobel; must be film, not ceramic |
| L1 | 2.2 µH air core | ~12 turns of 1.0 mm wire, 12 mm ID, wound over R36 |
| R36 | 10 Ω 3 W | damps L1 |

Pre-driver collectors go to the ±30 V front-end rails, not the ±24 V main rails. This
is what lets the output emitters get within about 2.5 V of the main rail: the driver
bases need to sit roughly 2 V above the output, and if they were fed from the same rail
as the output collectors they would run out of headroom first.

The ceiling that remains is set by the ballast and the output device's own saturation.
Simulation puts it at 21.4 V peak at the speaker terminals, and the arithmetic agrees:
at the 2 Ω peak of 10.7 A the two paralleled 0.22 Ω ballasts drop 1.18 V, leaving about
1.4 V of `Vce(sat)` in the output device. §2.3 gives the resulting power.

Base current chain at the 2 Ω peak of 10.9 A: 5.45 A per output device at hFE ≈ 40 needs
136 mA of base drive each, so 272 mA out of the driver emitter; the driver at hFE ≈ 60
needs 4.5 mA from the pre-driver, which is 0.3 % of the `TTC004B` rating. That is the
whole point of the triple.

### Feedback network and DC servo

| Ref | Part / value | Notes |
|---|---|---|
| R37 | 2.2 kΩ 0.1 % thin film, 0.5 W | feedback upper leg |
| R38 | 115 Ω 0.1 % thin film | feedback lower leg — gain = 20.13 V/V |
| C14 | 10 pF C0G | across R37; RF ingress guard, *not* a bandwidth limit — see §2.3 |
| U2 | `OPA1642` dual JFET op-amp | DC servo, one per channel, ±15 V |
| R44 | 470 kΩ | servo integrator input |
| C15 | 2.2 µF film (`WIMA MKS4` or PPS) | integrator, τ = 1.03 s |
| R45, R49 | 1 kΩ | servo non-inverting input references |
| R46, R47 | 100 kΩ 1 % | unity-gain inverter |
| C16 | 100 nF | across R47, limits servo bandwidth to 16 Hz |
| R48 | 10 kΩ | injects correction into the `FB` node |
| R43 | 100 kΩ | output DC sense to the protection block |

The servo is two stages because the polarity demands it. Injecting current into the
feedback summing node moves the output in the opposite direction, so the servo must be
*non-inverting* overall: `U2A` integrates, `U2B` inverts. A single inverting integrator
driving `FB` would be positive feedback and would latch the amplifier to a rail.

Authority is ±2.86 V referred to the output, from ±13 V of servo swing through R48 into
the 109 Ω feedback node. Noise cost is negligible — because the feedback node is a low
impedance, the injection resistor's noise current develops only about 0.07 nV/√Hz there.

## 2.3 Electrical performance

Two kinds of number appear below and they should not be confused. Hand calculations
come from `tools/design_calcs.py`. Simulated figures come from ngspice via
`python tools/sim_sweep.py stability` and `... thd`, on the netlist generated from
`tools/channel_netlist.py`, so they describe the circuit as actually drawn.

| Parameter | Hand calc | Simulated |
|---|---|---|
| Closed-loop gain | 20.13 V/V (26.1 dB) | 19.85 V/V (25.95 dB) |
| Open-loop unity gain | — | 8.2–8.4 MHz |
| Unity **loop** gain frequency | — | 456 kHz |
| Loop gain at 1 kHz / 20 kHz | — | 53 dB / 27 dB |
| Phase margin, worst load | — | 88.7° |
| Gain margin, worst load | — | 13.1 dB |
| Closed-loop −3 dB | — | 93 kHz (2 Ω) to 158 kHz |
| Input stage transconductance | 2.146 mS | — |
| Input-referred noise | ~2.84 nV/√Hz | — |
| Output noise, 22 kHz bandwidth | ~8.5 µV RMS | — |
| Quiescent current, output stage | 45 mA per device | 44.5 mA |

Distortion, at the speaker terminals, 10 harmonics:

| Condition | THD | Dominant harmonic |
|---|---|---|
| 1 kHz, 4 Ω, 52 W | 0.0013 % | 3rd at 0.0008 % |
| 1 kHz, 2 Ω, 105 W | 0.0017 % | 5th at 0.0010 % |
| 20 kHz, 4 Ω, 52 W | 0.0245 % | 3rd at 0.0173 % |
| 20 kHz, 2 Ω, 105 W | 0.0545 % | 3rd at 0.0477 % |
| 1 kHz, 4 Ω, 1 W | 0.0008 % | 3rd at 0.0007 % |

Treat these as a floor rather than a prediction. The simulation has no layout coupling,
no supply ripple, no output-stage thermal modulation and idealised device models; the
measured article will be worse, and the gap between the two is a layout report card.
The useful information here is the *shape*: distortion is third-harmonic dominated and
rises with frequency, which is what a well-compensated EF3 with plenty of loop gain
should look like. A large second harmonic on the bench would mean an asymmetry that is
not in the schematic.

### Output before clipping

The rails are regulated, so these numbers do not move with battery voltage — what clips
at 14.4 V input clips identically at 11 V. That is the main audible payoff of the
regulated supply, and it is why the table has one row per load rather than a range.

| Load | 0.01 % THD | 0.1 % THD | 1 % THD |
|---|---|---|---|
| 4 Ω | 22.3 V peak / 62 W | 22.5 V peak / 63 W | 22.7 V peak / 64 W |
| 2 Ω | 21.3 V peak / 113 W | 21.5 V peak / 116 W | 21.7 V peak / 118 W |

Clipping is a hard ceiling, not a soft knee: THD goes from 0.002 % to 16 % across about
2 % of drive level, because the output simply runs into the rail minus the ballast drop
minus `Vce(sat)`. There is no graceful overload region to lean on, so the 2 Ω midbass
channel should be treated as a **113 W** channel. An earlier revision of this
documentation claimed 119 W into 2 Ω, which needs 21.8 V peak — above the 21.4 V ceiling,
so that figure was on the wrong side of hard clipping and has been corrected everywhere.

### There is no slew rate limit

`design_calcs.py` reports Itail/Cdom = 4 mA / 68 pF = 58.8 V/µs, and it is tempting to
quote that as the slew rate. Simulation says the amplifier never gets near it, so the
number is not a limit that exists in this design.

The check is to drive a full-output square wave, then the same square wave ten times
smaller, and compare slope per volt of step. Slew limiting means the edge takes a fixed
time however small the step, so slope per volt would fall by ten. Measured, it changes
by 0.2 %: 0.3002 V/µs per volt at 20.5 V versus 0.2996 at 2.05 V. The edge is a linear
bandwidth-limited exponential all the way to full output.

So the correct statement is that the closed-loop risetime is 2.7 µs into 4 Ω and 3.7 µs
into 2 Ω from the worst-case 2.5 kΩ trimmer source impedance, and that slew limiting
never occurs. Anyone re-measuring this on the bench and reporting "6 V/µs slew rate"
has measured the risetime, not a slew limit.

### Step response and settling

| Load | Risetime | Overshoot | Ringing |
|---|---|---|---|
| 4 Ω | 2.66 µs | 0.00 % | 0.00 % |
| 2 Ω | 3.65 µs | 0.00 % | 0.00 % |
| 2 Ω + 100 nF | 3.34 µs | 0.00 % | 0.00 % |
| 2 Ω + 470 nF | 2.62 µs | 4.3 % | 0.02 % |
| 2 Ω + 2.2 µF | 3.35 µs | 28.7 % | 12.2 % |

Zero overshoot into resistive loads and into 100 nF, which is what 89° of phase margin
predicts. The 2.2 µF row is not a stability problem: the loop margins are unchanged at
90.1° and 13.8 dB, and what is being seen is L1 resonating with the load capacitance
*outside* the feedback loop, which R36 damps. It shows up in the AC sweep as closed-loop
peaking — 30.3 dB into 2 Ω + 2.2 µF and 38.5 dB into 8 Ω + 2.2 µF against a 26.0 dB
passband — and it is a property of the output filter, not of the amplifier. No real
speaker load looks like this; the case is included because an electrostatic tweeter or a
long unterminated cable is the nearest thing to it.

## 2.4 Signal-path purity notes

**The input is DC-coupled and there is no capacitor in the signal path.** `C6` is fitted
with a 0 Ω link. This is possible because the input stage's base current (6.7 µA) sees
only the trim network's source impedance of at most about 3.4 kΩ, giving roughly 23 mV
of input-referred offset which the servo removes easily. Had the input been AC-coupled
with a 100 kΩ bias resistor to ground, that same base current would develop 0.68 V of
input-referred offset — enough to drive the output to 13.7 V and saturate the input
stage. Any change to the input biasing must preserve this.

If your DSP has significant differential DC offset at its outputs, populate `C6` with a
2.2 µF film capacitor instead of the link; with R4 = 100 kΩ that gives a 0.72 Hz corner.

**There is no series muting device.** Turn-on thump and DC-fault isolation are handled by
the output relay, which is required for fault protection anyway. A DNP `BSS138` shunt
mute (`Q16`, `R5`) is provided at `AIN` for anyone who wants it; leaving it unpopulated
keeps 20 pF of nonlinear capacitance off the input node.

**No electrolytics in the loop.** The usual large electrolytic across the feedback lower
leg is replaced by the DC servo with a film integrator capacitor.

## 2.5 Net-to-pin connection table

This is the authoritative netlist for schematic generation. Pin names are used for ICs
and standard terminal letters for discretes (B/C/E, G/D/S, A/K) so the generating script
binds them from the KiCad symbol rather than from hard-coded pin numbers.

Sheet hierarchical pins: `IN_HOT`, `IN_COLD`, `SPK_OUT`, `VCC_MAIN`, `VEE_MAIN`,
`VCC_FE`, `VEE_FE`, `VCC_15`, `VEE_15`, `SIG_GND`, `PWR_GND`, `DC_SENSE`, `I_SENSE`.

### Input receiver

| Ref | Terminal | Net |
|---|---|---|
| R1 | 1 / 2 | `IN_HOT` / `U1.IN+` |
| R2 | 1 / 2 | `IN_COLD` / `U1.IN-` |
| U1 | IN+ | `RX_INP` (= R1.2) |
| U1 | IN- | `RX_INN` (= R2.2) |
| U1 | COM | `SIG_GND` |
| U1 | REF | `SIG_GND` |
| U1 | VMID(IN) | `VMID` |
| U1 | VMID(OUT) | unconnected |
| U1 | OUT | `RX` |
| U1 | VCC | `VCC_15` |
| U1 | VEE | `VEE_15` |
| C1 | 1 / 2 | `VMID` / `SIG_GND` |
| C2 | 1 / 2 | `VCC_15` / `SIG_GND` |
| C3 | 1 / 2 | `VCC_15` / `SIG_GND` |
| C4 | 1 / 2 | `VEE_15` / `SIG_GND` |
| C5 | 1 / 2 | `VEE_15` / `SIG_GND` |
| R7 (DNP) | 1 / 2 | `U1.COM` / `SIG_GND` |

### Gain trim and input node

| Ref | Terminal | Net |
|---|---|---|
| R3 | 1 / 2 | `RX` / `TRIM_TOP` |
| RV1 | 1 / 3 / 2 (wiper) | `TRIM_TOP` / `SIG_GND` / `TRIM` |
| C6 | 1 / 2 | `TRIM` / `AIN` (0 Ω link default) |
| R4 | 1 / 2 | `AIN` / `SIG_GND` |
| R6 | 1 / 2 | `AIN` / `LTP_INP` |
| C7 | 1 / 2 | `LTP_INP` / `SIG_GND` |
| Q16 (DNP) | D / S / G | `MUTE_NODE` / `SIG_GND` / `MUTE_CTL` |
| R5 (DNP) | 1 / 2 | `AIN` / `MUTE_NODE` |

### Input stage

| Ref | Terminal | Net |
|---|---|---|
| Q1A | B / E / C | `LTP_INP` / `Q1A_E` / `LC_A` |
| Q1B | B / E / C | `FB` / `Q1B_E` / `LC_B` |
| R8 | 1 / 2 | `Q1A_E` / `TAIL` |
| R9 | 1 / 2 | `Q1B_E` / `TAIL` |
| Q2 | B / E / C | `TREF` / `Q2_E` / `TAIL` |
| R10 | 1 / 2 | `VCC_FE` / `Q2_E` |
| D1 | A / K | `VCC_FE` / `TREF` |
| R11 | 1 / 2 | `TREF` / `SIG_GND` |
| C8 | 1 / 2 | `TREF` / `VCC_FE` |
| Q3A | B / E / C | `MB` / `Q3A_E` / `LC_A` |
| Q3B | B / E / C | `MB` / `Q3B_E` / `LC_B` |
| R12 | 1 / 2 | `Q3A_E` / `VEE_FE` |
| R13 | 1 / 2 | `Q3B_E` / `VEE_FE` |

`MB` is shorted to `LC_B`, diode-connecting `Q3B`. This orientation is what makes the
loop negative-feedback: signal enters `Q1A`, the mirror output `LC_A` drives the VAS, and
feedback returns to `Q1B`. Reversing the diode side inverts the amplifier and the loop
becomes positive feedback.

### VAS

| Ref | Terminal | Net |
|---|---|---|
| Q4 | B / C / E | `LC_A` / `VCC_FE` / `VB_PRE` |
| R14 | 1 / 2 | `VB_PRE` / `VEE_FE` |
| R18 | 1 / 2 | `VB_PRE` / `Q5_B` |
| Q5 | B / C / E | `Q5_B` / `BIAS_BOT` / `Q5_E` |
| R15 | 1 / 2 | `Q5_E` / `VEE_FE` |
| C9 | 1 / 2 | `BIAS_BOT` / `LC_A` |
| R16 (DNP) | 1 / 2 | `BIAS_BOT` / `TP_NODE` |
| C10 (DNP) | 1 / 2 | `TP_NODE` / `LC_A` |
| Q6 | B / E / C | `CSREF` / `Q6_E` / `BIAS_TOP` |
| R19 | 1 / 2 | `VCC_FE` / `Q6_E` |
| D2 | A / K | `VCC_FE` / `CSREF` |
| R20 | 1 / 2 | `CSREF` / `SIG_GND` |
| C11 | 1 / 2 | `CSREF` / `VCC_FE` |

### Bias spreader

| Ref | Terminal | Net |
|---|---|---|
| Q7 | C / E / B | `BIAS_TOP` / `BIAS_BOT` / `BADJ_W` |
| R21 | 1 / 2 | `BIAS_TOP` / `BADJ` |
| RV2 | 1 / 3 / 2 (wiper) | `BADJ` / `BADJ_L` / `BADJ_W` |
| R22 | 1 / 2 | `BADJ_L` / `BIAS_BOT` |
| C12 | 1 / 2 | `BIAS_TOP` / `BIAS_BOT` |
| D3 | K / A | `BIAS_TOP` / `BIAS_BOT` |

### Output stage

| Ref | Terminal | Net |
|---|---|---|
| Q8 | B / C / E | `BIAS_TOP` / `VCC_FE` / `PD_N` |
| Q9 | B / C / E | `BIAS_BOT` / `VEE_FE` / `PD_P` |
| R23 | 1 / 2 | `PD_N` / `OUT_STAR` |
| R24 | 1 / 2 | `PD_P` / `OUT_STAR` |
| Q10 | B / C / E | `PD_N` / `VCC_MAIN` / `DR_N` |
| Q11 | B / C / E | `PD_P` / `VEE_MAIN` / `DR_P` |
| R25 | 1 / 2 | `DR_N` / `OUT_STAR` |
| R26 | 1 / 2 | `DR_P` / `OUT_STAR` |
| R27 | 1 / 2 | `DR_N` / `Q12_B` |
| R28 | 1 / 2 | `DR_N` / `Q13_B` |
| R29 | 1 / 2 | `DR_P` / `Q14_B` |
| R30 | 1 / 2 | `DR_P` / `Q15_B` |
| Q12 | B / C / E | `Q12_B` / `VCC_MAIN` / `Q12_E` |
| Q13 | B / C / E | `Q13_B` / `VCC_MAIN` / `Q13_E` |
| Q14 | B / C / E | `Q14_B` / `VEE_MAIN` / `Q14_E` |
| Q15 | B / C / E | `Q15_B` / `VEE_MAIN` / `Q15_E` |
| R31 | 1 / 2 | `Q12_E` / `OUT_STAR` |
| R32 | 1 / 2 | `Q13_E` / `OUT_STAR` |
| R33 | 1 / 2 | `Q14_E` / `OUT_STAR` |
| R34 | 1 / 2 | `Q15_E` / `OUT_STAR` |
| R35 | 1 / 2 | `OUT_STAR` / `ZOB` |
| C13 | 1 / 2 | `ZOB` / `PWR_GND` |
| L1 | 1 / 2 | `OUT_STAR` / `SPK_OUT` |
| R36 | 1 / 2 | `OUT_STAR` / `SPK_OUT` |

### Feedback, servo, sensing

| Ref | Terminal | Net |
|---|---|---|
| R37 | 1 / 2 | `OUT_STAR` / `FB` |
| R38 | 1 / 2 | `FB` / `SIG_GND` |
| C14 | 1 / 2 | `OUT_STAR` / `FB` |
| R44 | 1 / 2 | `OUT_STAR` / `SRV_A_IN` |
| U2A | IN- / IN+ / OUT | `SRV_A_IN` / `SRV_A_REF` / `SRV_A_OUT` |
| C15 | 1 / 2 | `SRV_A_IN` / `SRV_A_OUT` |
| R45 | 1 / 2 | `SRV_A_REF` / `SIG_GND` |
| R46 | 1 / 2 | `SRV_A_OUT` / `SRV_B_IN` |
| U2B | IN- / IN+ / OUT | `SRV_B_IN` / `SRV_B_REF` / `SRV_B_OUT` |
| R47 | 1 / 2 | `SRV_B_IN` / `SRV_B_OUT` |
| C16 | 1 / 2 | `SRV_B_IN` / `SRV_B_OUT` |
| R49 | 1 / 2 | `SRV_B_REF` / `SIG_GND` |
| R48 | 1 / 2 | `SRV_B_OUT` / `FB` |
| U2 | V+ / V- | `VCC_15` / `VEE_15` |
| C17 | 1 / 2 | `VCC_15` / `SIG_GND` |
| C18 | 1 / 2 | `VEE_15` / `SIG_GND` |
| R43 | 1 / 2 | `OUT_STAR` / `DC_SENSE` |
| R50 | 1 / 2 | `Q12_E` / `I_SENSE` |

`R50` (10 kΩ) taps one ballast resistor's high side so the protection block can watch for
bias runaway. See `docs/04-protection-and-control.md`.

### Local decoupling

| Ref | Value | Net A | Net B |
|---|---|---|---|
| C19 | 220 µF 35 V low-ESR | `VCC_MAIN` | `PWR_GND` |
| C20 | 220 µF 35 V low-ESR | `VEE_MAIN` | `PWR_GND` |
| C21 | 100 nF 100 V film | `VCC_MAIN` | `PWR_GND` |
| C22 | 100 nF 100 V film | `VEE_MAIN` | `PWR_GND` |
| C23 | 10 µF 50 V | `VCC_FE` | `SIG_GND` |
| C24 | 10 µF 50 V | `VEE_FE` | `SIG_GND` |
| C25 | 100 nF | `VCC_FE` | `SIG_GND` |
| C26 | 100 nF | `VEE_FE` | `SIG_GND` |

Note the split: main-rail decoupling returns to `PWR_GND` because it carries output-stage
current; front-end decoupling returns to `SIG_GND` because it does not.

## 2.6 Simulation checklist before layout

Do not lay this out before the channel simulates cleanly. Every check below runs from
the same generated netlist, so none of them can be passing against a different circuit
than the one being laid out:

```
python tools/gen_spice.py                 # channel_netlist.py -> sim/channel_core.net
python tools/sim_sweep.py verify           # bias setpoint and thermal tracking
python tools/sim_sweep.py stability        # loop margins across every load
python tools/sim_sweep.py thd              # distortion, headroom, step response
```

| # | Check | Status |
|---|---|---|
| 1 | **DC operating point** against §2.2; the mirror `Vce` of 2.16 V and the VAS emitter at −29 V are the two that reveal biasing mistakes | pass, 44.5 mA per device |
| 2 | **Loop gain and phase**, ≥ 60° phase margin into 2 Ω ∥ 2.2 µF | pass, 88.7° worst case, 13.1 dB gain margin |
| 3 | **Closed-loop step response**, 2 Ω, no sustained ringing | pass, 0.00 % overshoot into 2 Ω |
| 4 | **THD sweep**, 1 kHz and 20 kHz, 1 W and full power, 4 Ω and 2 Ω | pass, 0.0013 % to 0.0545 % |
| 5 | **Clipping behaviour** — no latch-up or sticking on hard clip, which is where three-stage designs with a beta-enhanced VAS can misbehave | pass, recovers; ceiling is a hard 21.4 V |
| 6 | **Bias stability sweep**, Q7 25 °C to 90 °C, 25–80 mA per device | pass, see `sim_sweep.py verify` |
| 7 | **Compensation sensitivity** to `TTC004B` Cob at datasheet extremes | **outstanding** — Cob tolerance is the main unknown now that the low-Cob parts are gone |

Two traps are worth knowing about before re-running any of this, because both produce
confident wrong answers rather than errors.

The 2 Ω DC operating point will not solve if the feedback loop is closed through a small
resistor. `gen_spice.py` splits Q1B's base onto its own node so the analysis deck decides
how to rejoin it, and rejoining it with a 1 mΩ resistor puts a near-singular row in the
matrix: ngspice then reports a 1.9 A bias point instead of 44.5 mA, and every distortion
figure taken afterwards is fiction. Close it with a 0 V source, which gets a proper branch
equation. All the decks in `sim_sweep.py` now do.

Do not change the load with `alter` and keep using the same ngspice process. `alter rload`
sets the resistance correctly, but the DC solve that follows lands on the same wrong 1.9 A
point, and nothing warns you. Each load case therefore gets its own process with the load
fixed at parse time. Every deck also asserts the bias current and the L1 residual before
it measures anything, so a bad solve fails loudly instead of being reported as 16 % THD.
