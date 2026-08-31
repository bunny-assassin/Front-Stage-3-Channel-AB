# 06 — Bring-Up and Test

Read this before applying power to anything. A ±24 V supply capable of 27 A of input
current will vaporise a bond wire before a fuse notices, and a bias error puts 60 W into
a transistor in under a second.

## 6.0 Bench requirements

| Item | Why |
|---|---|
| Current-limited bench supply, 0–15 V, 0–5 A | every first power-up |
| Second supply for ±30 V front-end testing | lets the front-end be validated with no output stage |
| Two-channel scope, ≥ 50 MHz, ×10 probes | oscillation lives at 1–20 MHz and a 10 MHz scope will not see it |
| Dummy loads: 4 Ω and 2 Ω, ≥ 200 W, non-inductive | wirewound loads have enough inductance to change stability results |
| Distortion analyser or a good USB interface plus REW/ARTA | acceptance testing |
| Thermal camera or 4× thermocouples | thermal validation |
| Variac or adjustable supply down to 10 V | cranking simulation |
| 2.2 µF film capacitor | worst-case capacitive load test |

**Always** insert 10 Ω 5 W fusible resistors in each main rail for first power-up of any
amplifier channel. They limit fault current to about 2.4 A, survive long enough to read a
meter, and cost less than an output device.

## 6.1 Stage 1 — PSU board, standalone

Do not connect the amp board. Full detail in `docs/03-psu-board.md` §3.7.

| Step | Check | Pass criteria |
|---|---|---|
| 1.1 | Controller only, MOSFETs not fitted, 12 V bench supply | 65 kHz ±5 %, dead time ~400 ns, **gate outputs 180° out of phase** |
| 1.2 | Transformer phasing with a signal generator into the primary | secondary halves in the expected polarity; mark and record |
| 1.3 | First power-up at 6 V through a 5 A limit, 100 Ω load | rails present, correct polarity, no smoke, MOSFETs cool |
| 1.4 | 12 V, resistive load stepped to 2 A per rail | ±24 V ±2 %, both rails within 0.3 V of each other |
| 1.5 | Drain waveform inspection | ringing peak below 60 V; tune snubber R |
| 1.6 | Load regulation, 0 to full load | ±24 V held within 2 % |
| 1.7 | Line regulation, 10 V to 15 V input | rails held; duty cycle stays under 0.45 at 11 V |
| 1.8 | Full 250 W into resistive load, 30 min | transformer < 90 °C, MOSFETs < 90 °C, rectifiers < 110 °C |
| 1.9 | Deliberate overload | overcurrent trips, recovers cleanly, nothing damaged |
| 1.10 | Output ripple at full load | < 50 mV pk-pk at 65 kHz on ±24 V |
| 1.11 | Aux rails | ±30 V and ±15 V correct across the full input range |

Step 1.1 is the one that matters most. In-phase gate outputs short the primary through
both switches and destroy all four MOSFETs on the first cycle. Verify with a scope, on
the actual board, before fitting them.

## 6.2 Stage 2 — One amplifier channel, front-end only

Fit everything except `Q10`–`Q15` (drivers and outputs). Power the front-end from a bench
supply at ±30 V, and the ±15 V rails from the regulators.

| Step | Check | Pass criteria |
|---|---|---|
| 2.1 | Current draw | front-end draws ~15 mA per rail |
| 2.2 | DC nodes against `docs/02` §2.2 | `TREF` +28.2 V, Q2 emitter +28.85 V, mirror bases −29.2 V, Q5 base −28.35 V, `LC_A` −27.7 V |
| 2.3 | Mirror collector-emitter voltage | `Q3A` Vce ≈ 2.16 V — **if this is below 0.5 V the mirror is saturated and the diode side is on the wrong collector** |
| 2.4 | VAS current | 10 mA through `Q5`, 1.0 V across `R15` |
| 2.5 | Bias spreader with `Q7` at room temperature | 3.7–5 V adjustable across `BIAS_TOP`–`BIAS_BOT`; set to 3.92 V |
| 2.6 | Servo | `SRV_B_OUT` settles near 0 V; output offset within ±20 mV |
| 2.7 | Small-signal gain, 100 mV input, no load | 20.1 V/V ±2 % |
| 2.8 | Line receiver CMRR | inject 1 V common mode at 1 kHz; > 80 dB rejection at the output |

Step 2.3 catches the single most likely schematic error in this topology. The current
mirror's diode-connected side must be `Q3B`, loading `Q1B`'s collector, with the VAS
driven from `LC_A`. Getting it backwards makes the feedback positive and the amplifier
latches to a rail.

## 6.3 Stage 3 — Full channel, first power-up

Fit drivers and outputs. Set `RV2` (bias trim) to **minimum spread** before applying
power. Rails through 10 Ω fusible resistors. No load, no speaker.

| Step | Check | Pass criteria |
|---|---|---|
| 3.1 | Power up, watch rail resistor drops | quiescent current under 100 mA total; if the resistors glow, stop |
| 3.2 | Output DC offset | within ±20 mV after the servo settles |
| 3.3 | Bias adjust: measure across one 0.22 Ω ballast resistor, creep upward | set to **9.9 mV** = 45 mA per device |
| 3.4 | Thermal soak 20 min, re-check bias | stays within 25–80 mA per device |
| 3.5 | Remove rail resistors, repeat 3.2–3.4 | same |
| 3.6 | Scope the output, no signal, 20 MHz bandwidth | no oscillation; noise floor only |
| 3.7 | 1 kHz at 1 W into 4 Ω | clean sine, no crossover notch visible on the residual |

### Bias setting procedure

Measure across **one** ballast resistor, not across the emitter-to-output pair. Target
9.9 mV (45 mA). Set it with the heatsink at room temperature, let it soak for 20 minutes
at idle, then re-check and re-trim. Repeat until stable. Expect bias to rise on first
soak; `Q7` over-compensates once the heatsink is warm, which is the safe direction.

If bias climbs continuously and will not settle, `Q7` does not have adequate thermal
contact with the heatsink. Do not work around this by setting bias low.

## 6.4 Stage 4 — Stability

The tests most likely to reveal a layout problem. Run every one on every channel.

| Step | Test | Pass criteria |
|---|---|---|
| 4.1 | Square wave 10 kHz, 4 Ω, 1 W | one overshoot cycle maximum, no sustained ringing |
| 4.2 | Square wave 10 kHz, 2 Ω | same |
| 4.3 | **2 Ω in parallel with 2.2 µF** | no oscillation; this is the worst realistic load and where marginal designs fail |
| 4.4 | Open-circuit output, full drive | stable |
| 4.5 | Sine sweep 20 Hz–100 kHz at 10 W, watch for HF peaking | response flat within 0.5 dB to 20 kHz, no peak before rolloff |
| 4.6 | Hard clipping, 1 kHz and 10 kHz | recovers immediately, no sticking or latch-up |
| 4.7 | Scope each output device base for local oscillation | none — if present, `R27`–`R30` base stoppers are the fix |

If 4.3 oscillates, the causes in order of likelihood are: output inductor value too low,
Zobel return path too long, or the compensation capacitor `C9` too small for the actual
`TTC004B` Cob. Change one thing at a time and re-run the simulation to match.

## 6.5 Stage 5 — Protection

Test every protection path deliberately. Untested protection is decoration.

| Step | Test | Pass criteria |
|---|---|---|
| 5.1 | Inject +3 V DC at the amplifier input through 10 kΩ | relay opens within ~1 s, red LED, latched |
| 5.2 | Same, negative polarity | same |
| 5.3 | Heat the NTC to 85 °C | relays open, amber LED, re-close at 70 °C |
| 5.4 | Short the output at 1/3 power | latch within ~10 ms, no device damage |
| 5.5 | Force bias high with `RV2` | bias runaway detector latches above 150 mV across the ballast |
| 5.6 | Remove `Q7` to emulate open-circuit failure | `D3` clamps the spread at ~5.1 V and the runaway detector latches. **Use rail resistors for this test.** |
| 5.7 | Turn-on | no thump; relays close at ~2.5 s |
| 5.8 | Turn-off, remote removed | relays open before the rails collapse; no thump |
| 5.9 | Rail asymmetry: disconnect one rail | relays open |
| 5.10 | Cranking simulation: input 15 V → 10 V under load | no mute, no thump, rails hold |

## 6.6 Stage 6 — Acceptance measurements

Per channel, at its design load. These are the numbers to record and keep.

| Measurement | Condition | Target |
|---|---|---|
| Power at 1 % THD | 4 Ω / 4 Ω / 2 Ω | ≥ 55 W / 55 W / 110 W |
| THD+N | 1 kHz, half power | < 0.003 % |
| THD+N | 20 kHz, half power | < 0.01 % |
| THD+N | 1 kHz, 1 W | < 0.005 % |
| IMD, SMPTE | half power | < 0.005 % |
| Frequency response | 1 W | 20 Hz–20 kHz within ±0.1 dB |
| Signal-to-noise | A-weighted, ref full output | > 110 dB |
| Residual noise | input shorted, 22 kHz BW | < 30 µV |
| **Switching residue at 65 kHz** | speaker terminals, full power | < −90 dBV |
| Channel separation | 1 kHz | > 80 dB |
| Damping factor | 100 Hz | > 200 |
| DC offset | after 30 min soak | < 20 mV |
| Crosstalk between units | left driven, right measured | > 90 dB |

The 65 kHz switching residue figure is the one that validates the whole two-board,
shielded, interwinding-shield, synced-converter architecture. If it fails, the causes in
order are: missing or wrongly grounded interwinding shield in T1, secondary rectifier
loop area, or `PWR_GND`/`SIG_GND` joined at more than one point.

## 6.7 Stage 7 — Both units together

| Step | Test | Pass criteria |
|---|---|---|
| 7.1 | Both units powered, sync line **disconnected** | note any wandering low-frequency tone or beat in the residual |
| 7.2 | Sync line **connected** | beat products gone; converters phase-locked |
| 7.3 | Full power both units, 30 min, in-chassis | heatsink < 75 °C, no thermal trip |
| 7.4 | Total current draw | ~40 A at full output; verify wiring and fuses do not sag |
| 7.5 | In-vehicle: engine off, engine running, headlights and blower on | no change in noise floor, no alternator whine |
| 7.6 | AM radio tuned across the band, amplifiers running | no birdies from the 65 kHz converter harmonics |

Test 7.1 versus 7.2 is worth doing in that order, so you hear what the sync line buys.

## 6.8 Failure triage

| Symptom | Most likely cause |
|---|---|
| Output latched to a rail | current mirror diode side reversed (see 2.3) |
| Oscillation at 1–20 MHz | base stoppers missing, or `C9` too small for actual Cob |
| Oscillation only with capacitive load | output inductor value, or Zobel return length |
| Bias will not stabilise | `Q7` thermal contact |
| Hum at 100 Hz | more than one `SIG_GND`/`PWR_GND` connection |
| Hiss higher than expected | `R48` servo injection too small, or `SIG_GND` carrying load current |
| 65 kHz at the output | interwinding shield, or rectifier loop area |
| Wandering tone with both units on | sync line not connected |
| Distortion rising at low impedance only | ballast resistors mismatched, or one output pair not sharing |
| Turn-off thump | remote-loss detector too slow relative to rail decay |
| Protection trips on bass | `DC_SENSE` routed near a speaker output |
