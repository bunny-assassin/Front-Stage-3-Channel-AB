# Deviations from AGENT_BRIEF / docs/07

Recorded while implementing Phase 1. Do not silently fold these back.

1. **Ballast footprint is `R_TO220-2_PWR221T`, not axial MPC71.** The live BoM
   orders Bourns `PWR221T-20-R220F` (and the 10 Ω Zobel in the same family).
   `R_Axial_MPC71_3W` remains in the library as an alternate. `channel_netlist.py`
   points at the TO-220-2.

2. **T1 footprint is the 18-pin Ferroxcube `CPH-ETD44-1S-18P`, not a 10-pin
   `CSH-ETD44-1S-10P`.** Current Ferroxcube catalogues list the 18-pin former.
   Only the pins the winding actually uses will be connected; unused pins stay NC.

3. **Fuse holder is Littelfuse `178.6165.0001` (PCB, 4-pin, 30 A), not
   `0FHM0002XP`.** The latter is an in-line wire holder and has no PCB footprint.

4. **`TO-247-3_Vertical_HeatsinkWall` was added** for the PSU `STPS40H100CW`
   rectifiers. Same wall-mount convention as the amp-board devices.

5. **`C_Film_P10.00mm` was added** for the MKS4 1 µ / 10 mm pitch parts. The
   docs/07 name `C_Film_10mm_P15.00mm` is kept for the 15 mm 2µ2 servo cap.

6. **Omron `G4A-1A-PE DC12` has no footprint yet.** The pin pattern is unique
   and is not G8P. It waits on a traced Omron mechanical drawing. Guessing it
   costs a board spin.

7. **No 3D models in this library.** Wall-mount STEP comes from the chassis CAD
   in phase 6. Reasons per footprint are in `lib/README.md`.

8. **KiCad 10 symbol lib_ids.** `Device:Q_NPN_BCE` / `Q_PNP_BCE` / `Q_NMOS_GDS`
   moved to `Transistor_BJT` / `Transistor_FET`. `INA1651` is `FS3W:INA1651`.
   The servo is drawn with `Amplifier_Operational:TL072` (value still OPA1642):
   KiCad 10 has no OPA1642 symbol, and embedding `Opamp_Dual` makes
   `kicad-cli` refuse to load the schematic. Pinout is the standard dual SOIC-8.

9. **Phase 2 ERC waivers (placeholder sheets).** `amp_channel.kicad_sch` is
   pin-accurate and is compared net-by-net to `channel_netlist.py`. Regulators,
   protection, interface, and the PSU project place BoM parts with labels next
   to symbols, not on pins — they have no Python netlist yet. `check_schematic.py`
   waives `pin_not_connected`, `label_dangling`, `pin_not_driven`, and
   `power_pin_not_driven` on those sheets, plus the channel mute FET gate
   (`Q116`/`Q216`/`Q316`) which is driven from the protection sheet. Nets with
   two to four connections are wired with a stub-then-jog router that refuses
   any segment within 0.64 mm of a foreign pin; high-fanout nets stay
   labels-only (docs/07). `kicad-sch-api`'s 90°/270° pin transform is swapped
   versus KiCad 10, so the generator inverts those angles when placing labels.

10. **Phase 3 placement.** Heatsink row coordinates match docs/05 §5.4 exactly.
    `Q7` is `NJW0281G` (TO-3P) in the netlist; the drill table assumed a TO-126
    TTC004B. Courtyard overlap against the adjacent drivers is waived. Input and
    speaker terminals use Phoenix MKDS 5.08 mm footprints (KiCad 10 has no
    `TerminalBlock_bornier-*`). Relays still have no G4A footprint. The board is
    placed, not routed — Phase 4.
