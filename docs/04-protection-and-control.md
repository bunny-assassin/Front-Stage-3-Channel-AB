# 04 — Protection and Control

All analogue and discrete. No microcontroller: nothing to boot, nothing to hang, no clock
or firmware noise inside a chassis full of millivolt-level analogue, and the failure modes
are all inspectable with a meter.

This block lives on the amp board and drives the output relays plus the PSU shutdown line.

## 4.1 Faults covered

| Fault | Detector | Response | Recovery |
|---|---|---|---|
| DC at a speaker output | per-channel complementary pair, ~1 s time constant | latch, all relays open, PSU shutdown | power cycle |
| Bias runaway / thermal runaway | ballast-resistor DC sense vs 150 mV | latch, relays open, PSU shutdown | power cycle |
| Heatsink over-temperature | 10 kΩ NTC + comparator, 85 °C trip | relays open, PSU stays up | auto at 70 °C |
| Output short / overcurrent | ballast-resistor peak sense vs 1.2 V | latch after ~10 ms integration | power cycle |
| Primary overcurrent | PSU shunt comparator | pulse-by-pulse duty limit | continuous |
| Turn-on thump | 2.5 s relay delay | relays held open | automatic |
| Turn-off thump | remote-line loss detect | relays open immediately, ahead of rail collapse | automatic |
| Rail asymmetry / missing rail | window comparator on ±24 V | relays open | auto when rails valid |

## 4.2 DC offset detection

Per channel, and deliberately simple — a comparator-based window detector needs a stable
reference and adds two more failure modes, where the complementary-pair detector is six
parts and fails safe.

```
 OUT_STAR ──R43 100k──┬── C30 10µF ──┬── SIG_GND        (time constant ≈ 1 s)
                      │              │
                      ├──R51 22k──► Q30 base (NPN, BC847)   trips on positive DC
                      └──R52 22k──► Q31 base (PNP, BC857)   trips on negative DC

 Q30 collector ──┐
 Q31 collector ──┴──► FAULT_DC  (open-collector, wired-OR across all 3 channels)
```

`R43` and `C30` form a 1 s low-pass so that programme material below 20 Hz does not trip
the detector while genuine DC does. Each transistor's emitter returns to `SIG_GND` through
a resistor sized so the trip point lands near ±1.8 V at the output — well below the DC
level that damages a voice coil, and far above any offset the servo would allow in normal
operation.

Trip threshold rationale: a 4 Ω tweeter sees 1.8 V DC as 0.8 W of continuous dissipation,
which it survives for the ~20 ms the relay needs to open. A 2 Ω midbass at the same
threshold sees 1.6 W, likewise harmless briefly.

## 4.3 Bias runaway detection

The failure this catches: bias creeping up because `Q7` lost thermal contact with the
heatsink, or a shorted bias trimmer, or `Q7` failing open (in which case `D3` clamps the
spread at 5.1 V and the quiescent current rises to roughly 1.7 A per device).

`R50` (10 kΩ) taps the high side of one ballast resistor per channel into an RC with a
~0.5 s time constant, then into a comparator against 150 mV. 150 mV across 0.22 Ω is
680 mA of quiescent current — 15× the 45 mA design point, so no risk of nuisance trips,
and well below the current that damages anything.

This detector is why the zener `D3` is a viable failsafe rather than merely a slower way
to destroy the output stage.

## 4.4 Over-temperature

10 kΩ NTC (B = 3950) bonded to the heatsink between the midbass channel's output devices
— the hottest point, since that channel dissipates 29.2 W worst case against 14.6 W for
the others.

Comparator with hysteresis: open relays at 85 °C sink temperature, re-close at 70 °C. The
PSU is left running so the fans (if fitted) and the thermal mass keep working, and so the
amplifier recovers by itself rather than needing a power cycle for a condition that is not
a fault.

A separate 100 °C thermal switch in series with the relay coil supply is a cheap
independent backup that does not depend on the comparator or its reference.

## 4.5 Overcurrent

Peak sense on the same ballast tap as §4.3, but through a fast path: trip above 1.2 V
across a 0.22 Ω ballast resistor, which is 5.45 A in one device, i.e. 10.9 A in the
channel — exactly the 2 Ω clipping current. An integrator (~10 ms) prevents musical peaks
into a nominal 2 Ω load from latching the amplifier, while a genuine short trips it well
inside the output devices' SOA.

Note what is *not* here: there is no V-I limiter clamping the base drive during normal
operation. V-I limiters are a common cause of audible distortion at low impedance because
they engage on reactive load peaks. The design instead survives 2 Ω with SOA margin (two
pairs, 5.45 A per device against a 15 A / 250 V device) and treats genuine overcurrent as
a fault to be latched.

## 4.6 Turn-on and turn-off sequencing

```
 REMOTE 12 V ──┬── R/C 100k, 10µF ──► comparator ──► PSU SHUTDOWN release
               │                                     (converter starts, ~1 s soft start)
               │
               └── loss detector ──────────────────► immediate relay open
                                                     (before rails collapse)

 rails valid ──► window comparator ──┐
 2.5 s delay ────────────────────────┴──► AND ──► relay drivers ──► K1, K2, K3
 no fault latched ────────────────────┘
```

Sequence on turn-on: remote goes high, converter soft-starts over about 1 s, rails settle,
the DC servos settle over about 1 s, and at 2.5 s the relays close. Nothing reaches the
speakers until the DC offset has already been measured and found acceptable.

Sequence on turn-off: the remote-loss detector opens the relays *first*, using energy
still stored in the relay supply, before the rails collapse. Turn-off thump comes from
rails decaying at different rates while the outputs are still connected; opening first
eliminates it.

## 4.7 Output relays

| Ref | Part class | Notes |
|---|---|---|
| K1, K2, K3 | automotive SPST, 20–30 A, AgSnO₂ contacts, 12 V coil | one per channel |

Coil supply comes from `V_BATT` through the thermal switch, never from the audio rails —
a relay coil's collapse transient injected into ±24 V is audible.

Each coil gets a flyback diode and a series 100 Ω + 100 nF snubber across the contacts to
suppress the arc on opening.

**Optional:** two relays in parallel per channel halves contact resistance. At 10.9 A a
20 mΩ contact drops 0.22 V and dissipates 2.4 W; the amplifier's feedback loop corrects
for it (the tap is ahead of the relay), so the effect on distortion is negligible, but
paralleling reduces heating and long-term contact degradation on the midbass channel.
Recommended on channel 3 only.

## 4.8 Fault latch and indication

A two-transistor cross-coupled latch, set by any `FAULT_*` line and cleared only by loss
of the relay supply. Latch output does two things: pulls all relay drivers off, and pulls
the PSU `SHUTDOWN` line.

Indicators, mounted so they are visible without disassembly:

| LED | Meaning |
|---|---|
| green | rails valid, relays closed, normal operation |
| amber | thermal limit active, relays open, will recover |
| red | latched fault, power cycle required |

## 4.9 Component budget

Roughly 40 discretes, 2 quad comparators (`LM339` class, or `LM393` pairs), 3 relays and
the associated passives. Place this block in one corner of the amp board, referenced to
`SIG_GND`, with its sense lines routed as quiet signals — a `DC_SENSE` trace run beside a
speaker output will trip the protection on loud bass.
