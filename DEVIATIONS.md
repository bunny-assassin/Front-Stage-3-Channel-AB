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
