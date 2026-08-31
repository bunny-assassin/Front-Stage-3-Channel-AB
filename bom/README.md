# Bill of Materials

Two boards per unit, **two units total**, so multiply everything here by two for a
complete front stage.

| File | Contents |
|---|---|
| [`amp-board.csv`](amp-board.csv) | 3 amplifier channels, front-end regulators, protection block, connectors |
| [`psu-board.csv`](psu-board.csv) | push-pull converter, magnetics, input protection |
| [`pricing.csv`](pricing.csv) | orderable MPNs, 2–3 live sources, 1-pc USD, line totals |

## Sourcing status

Every semiconductor was checked for production status while writing this design. The
findings that changed the design:

| Part | Status | Consequence |
|---|---|---|
| `NJL3281D` / `NJL1302D` (ThermalTrak) | **discontinued** — marked as such in the February 2026 onsemi datasheet revision | Design uses conventional output devices with a heatsink-mounted Vbe multiplier instead of integrated bias-tracking diodes |
| `KSA1381` / `KSC3503` | **end of life** | `TTA004B` / `TTC004B` used instead, with compensation designed for their 12–17 pF Cob rather than the 2 pF of the originals |
| `NJW0281G` / `NJW0302G` | active, widely stocked | primary output devices |
| `MJE15032` / `MJE15033` | active | drivers |
| `SG3525A` | in production (onsemi and Microchip) | converter controller |
| `INA1650` / `INA1651` | active, both TSSOP-14 | line receivers |
| `OPA1642` | active | DC servo |

### Substitution warnings

**Do not substitute the VAS transistors casually.** Builders report instability when
dropping `TTA004B`/`TTC004B` into designs compensated for the low-Cob `KSA1381`/`KSC3503`.
This design goes the other way — it is compensated for the Toshiba parts from the start,
which means fitting a *lower*-Cob part (such as KEC `KTA1381`/`KTC3503`) is the change
that would need the compensation re-checked. Either family works; the simulation must
match what is fitted.

**Output device alternates,** in preference order: `MJL3281A`/`MJL1302A` (TO-264, higher
dissipation), then Toshiba `2SC5200`/`2SA1943` (TO-3P, but with a serious counterfeit
problem — authorised distributors only). Do not mix devices from different families within
one channel.

**The 0.22 Ω ballast resistors must be non-inductive.** A standard wirewound in this
position adds series inductance right at the output node and degrades HF stability.

**The Zobel capacitor and rail bypass capacitors must be film, not ceramic.** Class 2
ceramics are piezoelectric and microphonic, and in a car that is not a theoretical
concern.

**LEDs `D1x1`/`D1x2` are voltage references, not indicators.** They set the current source
operating points via their ~1.8 V forward drop. Substituting a different colour changes
the tail and VAS currents. Red only.

## Cost estimate

Priced 30 August 2026 from live 1-piece USD at authorised distributors (DigiKey /
Mouser first, LCSC as a genuine-mfr second source, Newark / Farnell / RS as a third).
Line-by-line MPNs and the three quotes are in [`pricing.csv`](pricing.csv). Grouped
passives use a representative series price, not every value looked up individually.

This is what two boards actually cost if you order like a human building a pair of
units, not a factory:

| | Amp board | PSU board |
|---|---|---|
| Semiconductors + ICs | $114 | $32 |
| Passives (precision, film, electrolytics, ceramics) | $157 | $32 |
| Relays / magnetics / connectors / hardware | $77 | $65 |
| Bare PCB, 4-layer 2 oz outer, qty-5 buy | $55 | $50 |
| **Populated board** | **$403** | **$179** |

| | |
|---|---|
| Amp + PSU populated | $582 |
| Chassis / heatsink / leftover wire | $135 |
| **One unit (one stereo side)** | **$717** |
| **Complete front stage (2 units)** | **$1,435** |

The previous ~$560/unit guess was low. Three things moved it:

1. **Ballast resistors.** Twelve non-inductive 0.22 Ω parts at ~$3.80 (Bourns
   `PWR221T-20-R220F`) is $46 by itself. A wirewound is cheaper and wrong.
2. **Authorised output devices.** DigiKey onsemi `NJW0281G` is $5.12, not $2.
   Marketplace clones (EVVO, Inmark, Minos on LCSC) are $1–4.50 and are how
   people end up with fake TO-3Ps. Do not buy those.
3. **PCB.** 4-layer with 2 oz outer copper, in a 5-piece order, is ~$50–55 per
   board. Two pieces instead of five is closer to $80 each.

Buying the semiconductors from Mouser/Newark instead of DigiKey 1-pc trims about
$25/unit (`NJW0281G` $3.06 vs $5.12). Buying passives from LCSC (genuine Yageo /
Samsung / Vishay only) trims another ~$40. Neither changes the shape: this is a
~$700/side amplifier, not a $200 one.

The 4-layer 2 oz outer / 1 oz inner stackup is a paid upgrade at most fabs. Do not
accept the default 1 oz outer / 0.5 oz inner; it cannot carry these currents. See
`docs/05-pcb-layout.md` §5.1.

Excludes US tariffs (they apply on DigiKey/Mouser checkouts to the US), shipping,
the DSP, vehicle wiring, dummy loads, and spare output devices. Order at least
four extra of each NJW before bring-up (~$40).

### Parts the old BoM named that you cannot actually buy

| Old MPN | Status | Order this instead |
|---|---|---|
| Omron `G8P-1A4P` | discontinued 2016 | `G4A-1A-PE DC12` (20 A, different footprint) |
| onsemi `SG3525AN` DIP | obsolete / NCNR | `SG3525ADWR2G` SOIC-16W |
| `3296W-1-102LF` 1 kΩ bias trim | wrong value | `3296W-1-101LF` 100 Ω (see docs/02) |
| Vishay MPC71 0.22 Ω axial | scarce / often inductive | Bourns `PWR221T-20-R220F` or Caddock `MP930-0.20-1%` |

## Things to order early

Long lead or easily overlooked:

1. ETD44 core, clip set and bobbin, plus copper foil and litz/bundle wire — the
   transformer is the critical path and may need a second attempt.
2. Kool Mµ or sendust toroid for the coupled output choke.
3. 0.23 mm alumina insulator pads, 28 per unit — silicone pads will not meet the
   0.25 °C/W case-to-sink figure the thermal budget assumes.
4. Non-inductive 3 W power resistors, 18 per unit.
5. 4 Ω and 2 Ω 200 W non-inductive dummy loads for bring-up.
6. Chassis extrusion, which needs the STEP export from
   `docs/07-kicad-automation.md` phase 6 before it can be machined.
