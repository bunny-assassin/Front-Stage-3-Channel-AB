#!/usr/bin/env python3
"""Machine-readable netlist for one FS-3W amplifier channel.

This is the single source of truth for the channel schematic. docs/02 is the
human-readable form of the same data; if they disagree, this file wins because it
is validated.

    python3 tools/channel_netlist.py --check       validate connectivity
    python3 tools/channel_netlist.py --stats       component and net summary
    python3 tools/channel_netlist.py --netlist     emit a KiCad .net for one channel

The schematic generator (tools/gen_schematic.py) consumes COMPONENTS and NETLIST
directly, so a change here propagates to the schematic, the netlist and the BOM.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Component model
# ---------------------------------------------------------------------------


@dataclass
class Comp:
    ref: str
    value: str
    lib_id: str
    footprint: str
    pins: tuple[str, ...]
    desc: str = ""
    dnp: bool = False
    package_of: str | None = None   # for multi-section devices: shared package ref
    on_heatsink: bool = False
    tolerance: str = ""
    extra: dict = field(default_factory=dict)


R = "Device:R"
C = "Device:C"
CP = "Device:C_Polarized"
L = "Device:L"
POT = "Device:R_Potentiometer_Trim"
LED = "Device:LED"
ZEN = "Device:D_Zener"
NPN = "Device:Q_NPN_BCE"
PNP = "Device:Q_PNP_BCE"
NMOS = "Device:Q_NMOS_GDS"
OPA = "Amplifier_Operational:OPA1642"

# Footprint shorthands. Custom footprints marked FS3W: must be created, see docs/07.
F_0805 = "Resistor_SMD:R_0805_2012Metric"
F_1206 = "Resistor_SMD:R_1206_3216Metric"
F_C0805 = "Capacitor_SMD:C_0805_2012Metric"
F_SOT23 = "Package_TO_SOT_SMD:SOT-23"
F_SOT363 = "Package_TO_SOT_SMD:SOT-363_SC-70-6"
F_TSSOP14 = "Package_SO:TSSOP-14_4.4x5mm_P0.65mm"
F_SOIC8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
F_TO126 = "FS3W:TO-126N_Vertical_HeatsinkWall"
F_TO220 = "FS3W:TO-220-3_Vertical_HeatsinkWall"
F_TO3P = "FS3W:TO-3P_Vertical_HeatsinkWall"
F_BALLAST = "FS3W:R_Axial_MPC71_3W"
F_FILM_5 = "FS3W:C_Film_5mm_P5.00mm"
F_FILM_10 = "FS3W:C_Film_10mm_P15.00mm"
F_ELEC_10 = "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm"
F_TRIM = "Potentiometer_THT:Potentiometer_Bourns_3296W_Vertical"
F_IND_AIR = "FS3W:L_AirCore_12mm"

COMPONENTS: list[Comp] = [
    # ---- input receiver -------------------------------------------------
    Comp("R1", "100R", R, F_0805, ("1", "2"), "input series, RF/ESD", tolerance="0.1%"),
    Comp("R2", "100R", R, F_0805, ("1", "2"), "input series, RF/ESD", tolerance="0.1%"),
    Comp("R7", "1M", R, F_0805, ("1", "2"), "COM pin option, see docs/02", dnp=True),
    Comp("U1", "INA1651IPW", "Amplifier_Audio:INA1651", F_TSSOP14,
         ("IN+", "IN-", "COM", "REF", "VMID_IN", "VMID_OUT", "OUT", "VCC", "VEE"),
         "balanced line receiver, unity gain, 91 dB CMRR"),
    Comp("C1", "1u", C, F_C0805, ("1", "2"), "VMID bypass"),
    Comp("C2", "100n", C, F_C0805, ("1", "2"), "U1 +15V decoupling"),
    Comp("C3", "10u", C, F_C0805, ("1", "2"), "U1 +15V bulk"),
    Comp("C4", "100n", C, F_C0805, ("1", "2"), "U1 -15V decoupling"),
    Comp("C5", "10u", C, F_C0805, ("1", "2"), "U1 -15V bulk"),

    # ---- gain trim ------------------------------------------------------
    Comp("R3", "2k2", R, F_0805, ("1", "2"), "attenuator top", tolerance="0.1%"),
    Comp("RV1", "10k", POT, F_TRIM, ("1", "2", "3"), "gain trim, 25-turn cermet"),
    Comp("C6", "0R link", R, F_0805, ("1", "2"),
         "0R by default; 2u2 film if the source has DC offset"),
    Comp("R4", "100k", R, F_0805, ("1", "2"), "AIN pulldown"),
    Comp("R6", "1k", R, F_0805, ("1", "2"), "base stopper", tolerance="0.1%"),
    Comp("C7", "220p", C, F_C0805, ("1", "2"),
         "input pole; 723 kHz against R6 alone, 207 kHz once the trimmer "
         "wiper's 2.5k is included. Deliberate, see docs/02"),
    Comp("R5", "100R", R, F_0805, ("1", "2"), "mute shunt", dnp=True),
    Comp("Q16", "BSS138", NMOS, F_SOT23, ("G", "D", "S"), "mute FET", dnp=True),

    # ---- input LTP ------------------------------------------------------
    Comp("Q1A", "BCM857BS", PNP, F_SOT363, ("B", "C", "E"),
         "input LTP, matched dual PNP", package_of="Q1"),
    Comp("Q1B", "BCM857BS", PNP, F_SOT363, ("B", "C", "E"),
         "input LTP, matched dual PNP", package_of="Q1"),
    Comp("R8", "220R", R, F_0805, ("1", "2"), "LTP degeneration", tolerance="0.1%"),
    Comp("R9", "220R", R, F_0805, ("1", "2"), "LTP degeneration", tolerance="0.1%"),
    Comp("Q2", "BC857C", PNP, F_SOT23, ("B", "C", "E"), "tail current source, 4 mA"),
    Comp("R10", "287R", R, F_0805, ("1", "2"), "sets tail current", tolerance="0.1%"),
    Comp("D1", "LED_RED", LED, F_0805, ("A", "K"), "tail reference, 1.8 V"),
    Comp("R11", "15k", R, F_0805, ("1", "2"), "LED bias"),
    Comp("C8", "100n", C, F_C0805, ("1", "2"), "TREF decoupling"),

    # ---- current mirror -------------------------------------------------
    Comp("Q3A", "BCM847BS", NPN, F_SOT363, ("B", "C", "E"),
         "mirror, matched dual NPN", package_of="Q3"),
    Comp("Q3B", "BCM847BS", NPN, F_SOT363, ("B", "C", "E"),
         "mirror, diode-connected side", package_of="Q3"),
    Comp("R12", "68R", R, F_0805, ("1", "2"), "mirror degeneration", tolerance="0.1%"),
    Comp("R13", "68R", R, F_0805, ("1", "2"), "mirror degeneration", tolerance="0.1%"),

    # ---- VAS ------------------------------------------------------------
    Comp("Q4", "BC847C", NPN, F_SOT23, ("B", "C", "E"), "VAS beta enhancer"),
    Comp("R14", "10k", R, F_0805, ("1", "2"), "keeps Q4 conducting"),
    Comp("R18", "100R", R, F_0805, ("1", "2"), "Q5 base stopper"),
    Comp("Q5", "TTC004B", NPN, F_TO126, ("B", "C", "E"),
         "VAS, 160 V, Cob 12 pF, 10 mA"),
    Comp("R15", "100R", R, F_0805, ("1", "2"), "VAS degeneration"),
    # 68p, not the 150p the hand calculation suggested. Simulated phase margin at
    # 150p is 104 deg, which is 44 deg more than the design needs, and that excess
    # is paid for in loop gain: 150p leaves only 19.7 dB of feedback at 20 kHz,
    # where the output stage is least linear. 68p buys 6.9 dB back and still holds
    # 89 deg. See tools/sim_sweep.py comp.
    Comp("C9", "68p", C, F_C0805, ("1", "2"),
         "Cdom, Miller compensation", tolerance="C0G 5%"),
    Comp("R16", "1k", R, F_0805, ("1", "2"), "two-pole comp", dnp=True),
    Comp("C10", "1n", C, F_C0805, ("1", "2"), "two-pole comp", dnp=True),
    Comp("Q6", "TTA004B", PNP, F_TO126, ("B", "C", "E"), "VAS current-source load"),
    Comp("R19", "115R", R, F_0805, ("1", "2"), "sets VAS current", tolerance="0.1%"),
    Comp("D2", "LED_RED", LED, F_0805, ("A", "K"), "current source reference"),
    Comp("R20", "15k", R, F_0805, ("1", "2"), "LED bias"),
    Comp("C11", "100n", C, F_C0805, ("1", "2"), "CSREF decoupling"),

    # ---- bias spreader --------------------------------------------------
    # The multiplier ratio is not a free parameter: it is the thermal tracking
    # spec. It must equal the number of junctions in the bias string that sit at
    # the temperature Q7 senses. The string is Q8-Q10-Q12 and Q9-Q11-Q14, so all
    # six pre-driver/driver/output junctions have to be on the heatsink for a
    # single multiplier to work. That is why Q8 and Q9 are heatsink-mounted
    # despite dissipating under 100 mW -- they are there to be measured, not
    # cooled. See docs/02 section 2.3.
    # Q7 is an output device, not a small-signal part, and that is deliberate.
    # The spread it must hold is fixed, so the ratio is fixed at spread/Vbe7 --
    # the only way to move the ratio onto the tracking optimum is to change Q7's
    # Vbe, i.e. its die size. An NJW0281G lands the ratio at 6.09 against an
    # optimum of 5.94; a TTC004B would force 5.64 and let the bias double when
    # hot. Using the same die as the outputs also makes Q7 track their Vbe
    # tolerance, not just their temperature.
    Comp("Q7", "NJW0281G", NPN, F_TO3P, ("B", "C", "E"),
         "Vbe multiplier, ratio 6.09, bolted to heatsink between Q12 and Q14",
         on_heatsink=True),
    Comp("R21", "4k42", R, F_0805, ("1", "2"),
         "multiplier upper leg; with R22 this sets the tempco", tolerance="1%"),
    Comp("RV2", "100R", POT, F_TRIM, ("1", "2", "3"),
         "bias trim, 25-turn cermet. 100R not 1k: the ratio window that matters "
         "is narrow, and a 1k pot puts all of it inside an eighth of a turn"),
    Comp("R22", "1k", R, F_0805, ("1", "2"),
         "multiplier lower leg; also the minimum-spread limit", tolerance="1%"),
    Comp("C12", "100n", C, F_C0805, ("1", "2"), "spreader HF bypass"),
    Comp("D3", "BZX84C5V1", ZEN, F_SOT23, ("A", "K"),
         "failsafe spread clamp, see docs/02"),

    # ---- output triple --------------------------------------------------
    # Q8/Q9 are on the heatsink for thermal *sensing*, not cooling: their Vbe is
    # part of the bias string that Q7's multiplier has to track.
    Comp("Q8", "TTC004B", NPN, F_TO126, ("B", "C", "E"),
         "NPN pre-driver, on heatsink for bias tracking", on_heatsink=True),
    Comp("Q9", "TTA004B", PNP, F_TO126, ("B", "C", "E"),
         "PNP pre-driver, on heatsink for bias tracking", on_heatsink=True),
    Comp("R23", "2k2", R, F_1206, ("1", "2"), "pre-driver emitter load"),
    Comp("R24", "2k2", R, F_1206, ("1", "2"), "pre-driver emitter load"),
    Comp("Q10", "MJE15032", NPN, F_TO220, ("B", "C", "E"),
         "NPN driver", on_heatsink=True),
    Comp("Q11", "MJE15033", PNP, F_TO220, ("B", "C", "E"),
         "PNP driver", on_heatsink=True),
    Comp("R25", "220R", R, F_1206, ("1", "2"), "driver emitter load"),
    Comp("R26", "220R", R, F_1206, ("1", "2"), "driver emitter load"),
    Comp("R27", "4R7", R, F_1206, ("1", "2"), "output base stopper"),
    Comp("R28", "4R7", R, F_1206, ("1", "2"), "output base stopper"),
    Comp("R29", "4R7", R, F_1206, ("1", "2"), "output base stopper"),
    Comp("R30", "4R7", R, F_1206, ("1", "2"), "output base stopper"),
    Comp("Q12", "NJW0281G", NPN, F_TO3P, ("B", "C", "E"),
         "output NPN", on_heatsink=True),
    Comp("Q13", "NJW0281G", NPN, F_TO3P, ("B", "C", "E"),
         "output NPN", on_heatsink=True),
    Comp("Q14", "NJW0302G", PNP, F_TO3P, ("B", "C", "E"),
         "output PNP", on_heatsink=True),
    Comp("Q15", "NJW0302G", PNP, F_TO3P, ("B", "C", "E"),
         "output PNP", on_heatsink=True),
    Comp("R31", "0R22", R, F_BALLAST, ("1", "2"), "emitter ballast 3W"),
    Comp("R32", "0R22", R, F_BALLAST, ("1", "2"), "emitter ballast 3W"),
    Comp("R33", "0R22", R, F_BALLAST, ("1", "2"), "emitter ballast 3W"),
    Comp("R34", "0R22", R, F_BALLAST, ("1", "2"), "emitter ballast 3W"),
    Comp("R35", "10R", R, F_BALLAST, ("1", "2"), "Zobel resistor 3W"),
    Comp("C13", "100n/100V", C, F_FILM_5, ("1", "2"), "Zobel capacitor, film"),
    Comp("L1", "2u2", L, F_IND_AIR, ("1", "2"), "output inductor, air core"),
    Comp("R36", "10R", R, F_BALLAST, ("1", "2"), "damps L1"),

    # ---- feedback and servo --------------------------------------------
    Comp("R37", "2k2", R, F_1206, ("1", "2"), "feedback upper", tolerance="0.1%"),
    Comp("R38", "115R", R, F_0805, ("1", "2"), "feedback lower", tolerance="0.1%"),
    # 10p, not 100p. A cap across the feedback resistor raises the feedback factor
    # above its own corner, which flattens the loop gain into a shelf hanging just
    # under 0 dB. The phase keeps rotating through that shelf, so at 100p the loop
    # gain is still only -4 dB where the phase reaches -180 and the gain margin
    # collapses to 4.2 dB. At 10p the corner moves to 7.2 MHz, the shelf lands
    # where the gain has already gone, and the margin is 13.4 dB.
    Comp("C14", "10p", C, F_C0805, ("1", "2"),
         "feedback RF ingress guard; NOT a bandwidth limit, see docs/02 2.6",
         tolerance="C0G 5%"),
    Comp("U2A", "OPA1642", OPA, F_SOIC8, ("IN-", "IN+", "OUT"),
         "servo integrator", package_of="U2"),
    Comp("U2B", "OPA1642", OPA, F_SOIC8, ("IN-", "IN+", "OUT"),
         "servo inverter", package_of="U2"),
    Comp("U2P", "OPA1642", OPA, F_SOIC8, ("V+", "V-"),
         "servo power pins", package_of="U2"),
    Comp("R44", "470k", R, F_0805, ("1", "2"), "servo integrator input"),
    Comp("C15", "2u2", C, F_FILM_10, ("1", "2"), "servo integrator, film"),
    Comp("R45", "1k", R, F_0805, ("1", "2"), "servo reference"),
    Comp("R46", "100k", R, F_0805, ("1", "2"), "inverter input"),
    Comp("R47", "100k", R, F_0805, ("1", "2"), "inverter feedback"),
    Comp("C16", "100n", C, F_C0805, ("1", "2"), "limits servo to 16 Hz"),
    Comp("R49", "1k", R, F_0805, ("1", "2"), "servo reference"),
    Comp("R48", "10k", R, F_0805, ("1", "2"), "servo injection into FB"),
    Comp("C17", "100n", C, F_C0805, ("1", "2"), "U2 +15V decoupling"),
    Comp("C18", "100n", C, F_C0805, ("1", "2"), "U2 -15V decoupling"),

    # ---- sensing --------------------------------------------------------
    Comp("R43", "100k", R, F_0805, ("1", "2"), "DC offset sense"),
    Comp("R50", "10k", R, F_0805, ("1", "2"), "bias/overcurrent sense"),

    # ---- local decoupling ----------------------------------------------
    Comp("C19", "220u/35V", CP, F_ELEC_10, ("1", "2"), "main rail reservoir"),
    Comp("C20", "220u/35V", CP, F_ELEC_10, ("1", "2"), "main rail reservoir"),
    Comp("C21", "100n/100V", C, F_FILM_5, ("1", "2"), "main rail film"),
    Comp("C22", "100n/100V", C, F_FILM_5, ("1", "2"), "main rail film"),
    Comp("C23", "10u/50V", C, F_C0805, ("1", "2"), "front-end rail bulk"),
    Comp("C24", "10u/50V", C, F_C0805, ("1", "2"), "front-end rail bulk"),
    Comp("C25", "100n", C, F_C0805, ("1", "2"), "front-end rail decoupling"),
    Comp("C26", "100n", C, F_C0805, ("1", "2"), "front-end rail decoupling"),
]

# ---------------------------------------------------------------------------
# Connectivity: (ref, pin, net)
# ---------------------------------------------------------------------------

HIER_PINS = (
    "IN_HOT", "IN_COLD", "SPK_OUT", "VCC_MAIN", "VEE_MAIN", "VCC_FE", "VEE_FE",
    "VCC_15", "VEE_15", "SIG_GND", "PWR_GND", "DC_SENSE", "I_SENSE", "MUTE_CTL",
)

NETLIST: list[tuple[str, str, str]] = [
    # input receiver
    ("R1", "1", "IN_HOT"), ("R1", "2", "RX_INP"),
    ("R2", "1", "IN_COLD"), ("R2", "2", "RX_INN"),
    ("U1", "IN+", "RX_INP"), ("U1", "IN-", "RX_INN"),
    ("U1", "COM", "SIG_GND"), ("U1", "REF", "SIG_GND"),
    ("U1", "VMID_IN", "VMID"), ("U1", "VMID_OUT", "NC_VMID_OUT"),
    ("U1", "OUT", "RX"), ("U1", "VCC", "VCC_15"), ("U1", "VEE", "VEE_15"),
    ("R7", "1", "SIG_GND"), ("R7", "2", "SIG_GND"),
    ("C1", "1", "VMID"), ("C1", "2", "SIG_GND"),
    ("C2", "1", "VCC_15"), ("C2", "2", "SIG_GND"),
    ("C3", "1", "VCC_15"), ("C3", "2", "SIG_GND"),
    ("C4", "1", "VEE_15"), ("C4", "2", "SIG_GND"),
    ("C5", "1", "VEE_15"), ("C5", "2", "SIG_GND"),

    # gain trim
    ("R3", "1", "RX"), ("R3", "2", "TRIM_TOP"),
    ("RV1", "1", "TRIM_TOP"), ("RV1", "3", "SIG_GND"), ("RV1", "2", "TRIM"),
    ("C6", "1", "TRIM"), ("C6", "2", "AIN"),
    ("R4", "1", "AIN"), ("R4", "2", "SIG_GND"),
    ("R6", "1", "AIN"), ("R6", "2", "LTP_INP"),
    ("C7", "1", "LTP_INP"), ("C7", "2", "SIG_GND"),
    ("R5", "1", "AIN"), ("R5", "2", "MUTE_NODE"),
    ("Q16", "D", "MUTE_NODE"), ("Q16", "S", "SIG_GND"), ("Q16", "G", "MUTE_CTL"),

    # input LTP
    ("Q1A", "B", "LTP_INP"), ("Q1A", "E", "Q1A_E"), ("Q1A", "C", "LC_A"),
    ("Q1B", "B", "FB"), ("Q1B", "E", "Q1B_E"), ("Q1B", "C", "LC_B"),
    ("R8", "1", "Q1A_E"), ("R8", "2", "TAIL"),
    ("R9", "1", "Q1B_E"), ("R9", "2", "TAIL"),
    ("Q2", "B", "TREF"), ("Q2", "E", "Q2_E"), ("Q2", "C", "TAIL"),
    ("R10", "1", "VCC_FE"), ("R10", "2", "Q2_E"),
    ("D1", "A", "VCC_FE"), ("D1", "K", "TREF"),
    ("R11", "1", "TREF"), ("R11", "2", "SIG_GND"),
    ("C8", "1", "TREF"), ("C8", "2", "VCC_FE"),

    # current mirror. Q3B is the diode-connected side; reversing this inverts the
    # amplifier and turns the feedback positive.
    ("Q3A", "B", "LC_B"), ("Q3A", "E", "Q3A_E"), ("Q3A", "C", "LC_A"),
    ("Q3B", "B", "LC_B"), ("Q3B", "E", "Q3B_E"), ("Q3B", "C", "LC_B"),
    ("R12", "1", "Q3A_E"), ("R12", "2", "VEE_FE"),
    ("R13", "1", "Q3B_E"), ("R13", "2", "VEE_FE"),

    # VAS
    ("Q4", "B", "LC_A"), ("Q4", "C", "VCC_FE"), ("Q4", "E", "VB_PRE"),
    ("R14", "1", "VB_PRE"), ("R14", "2", "VEE_FE"),
    ("R18", "1", "VB_PRE"), ("R18", "2", "Q5_B"),
    ("Q5", "B", "Q5_B"), ("Q5", "C", "BIAS_BOT"), ("Q5", "E", "Q5_E"),
    ("R15", "1", "Q5_E"), ("R15", "2", "VEE_FE"),
    ("C9", "1", "BIAS_BOT"), ("C9", "2", "LC_A"),
    ("R16", "1", "BIAS_BOT"), ("R16", "2", "TP_NODE"),
    ("C10", "1", "TP_NODE"), ("C10", "2", "LC_A"),
    ("Q6", "B", "CSREF"), ("Q6", "E", "Q6_E"), ("Q6", "C", "BIAS_TOP"),
    ("R19", "1", "VCC_FE"), ("R19", "2", "Q6_E"),
    ("D2", "A", "VCC_FE"), ("D2", "K", "CSREF"),
    ("R20", "1", "CSREF"), ("R20", "2", "SIG_GND"),
    ("C11", "1", "CSREF"), ("C11", "2", "VCC_FE"),

    # bias spreader
    ("Q7", "C", "BIAS_TOP"), ("Q7", "E", "BIAS_BOT"), ("Q7", "B", "BADJ"),
    ("R21", "1", "BIAS_TOP"), ("R21", "2", "BADJ"),
    # RV2 pins 1 and 2 share a net on purpose: the wiper is strapped to the top
    # of the track, so a worn-open wiper leaves the whole track in the lower leg,
    # which is the minimum-bias direction. Wire the wiper to the free end and the
    # same failure commands maximum bias instead.
    ("RV2", "1", "BADJ"), ("RV2", "2", "BADJ"), ("RV2", "3", "BADJ_L"),
    ("R22", "1", "BADJ_L"), ("R22", "2", "BIAS_BOT"),
    ("C12", "1", "BIAS_TOP"), ("C12", "2", "BIAS_BOT"),
    ("D3", "K", "BIAS_TOP"), ("D3", "A", "BIAS_BOT"),

    # output triple
    ("Q8", "B", "BIAS_TOP"), ("Q8", "C", "VCC_FE"), ("Q8", "E", "PD_N"),
    ("Q9", "B", "BIAS_BOT"), ("Q9", "C", "VEE_FE"), ("Q9", "E", "PD_P"),
    ("R23", "1", "PD_N"), ("R23", "2", "OUT_STAR"),
    ("R24", "1", "PD_P"), ("R24", "2", "OUT_STAR"),
    ("Q10", "B", "PD_N"), ("Q10", "C", "VCC_MAIN"), ("Q10", "E", "DR_N"),
    ("Q11", "B", "PD_P"), ("Q11", "C", "VEE_MAIN"), ("Q11", "E", "DR_P"),
    ("R25", "1", "DR_N"), ("R25", "2", "OUT_STAR"),
    ("R26", "1", "DR_P"), ("R26", "2", "OUT_STAR"),
    ("R27", "1", "DR_N"), ("R27", "2", "Q12_B"),
    ("R28", "1", "DR_N"), ("R28", "2", "Q13_B"),
    ("R29", "1", "DR_P"), ("R29", "2", "Q14_B"),
    ("R30", "1", "DR_P"), ("R30", "2", "Q15_B"),
    ("Q12", "B", "Q12_B"), ("Q12", "C", "VCC_MAIN"), ("Q12", "E", "Q12_E"),
    ("Q13", "B", "Q13_B"), ("Q13", "C", "VCC_MAIN"), ("Q13", "E", "Q13_E"),
    ("Q14", "B", "Q14_B"), ("Q14", "C", "VEE_MAIN"), ("Q14", "E", "Q14_E"),
    ("Q15", "B", "Q15_B"), ("Q15", "C", "VEE_MAIN"), ("Q15", "E", "Q15_E"),
    ("R31", "1", "Q12_E"), ("R31", "2", "OUT_STAR"),
    ("R32", "1", "Q13_E"), ("R32", "2", "OUT_STAR"),
    ("R33", "1", "Q14_E"), ("R33", "2", "OUT_STAR"),
    ("R34", "1", "Q15_E"), ("R34", "2", "OUT_STAR"),
    ("R35", "1", "OUT_STAR"), ("R35", "2", "ZOB"),
    ("C13", "1", "ZOB"), ("C13", "2", "PWR_GND"),
    ("L1", "1", "OUT_STAR"), ("L1", "2", "SPK_OUT"),
    ("R36", "1", "OUT_STAR"), ("R36", "2", "SPK_OUT"),

    # feedback and servo
    ("R37", "1", "OUT_STAR"), ("R37", "2", "FB"),
    ("R38", "1", "FB"), ("R38", "2", "SIG_GND"),
    ("C14", "1", "OUT_STAR"), ("C14", "2", "FB"),
    ("R44", "1", "OUT_STAR"), ("R44", "2", "SRV_A_IN"),
    ("U2A", "IN-", "SRV_A_IN"), ("U2A", "IN+", "SRV_A_REF"),
    ("U2A", "OUT", "SRV_A_OUT"),
    ("C15", "1", "SRV_A_IN"), ("C15", "2", "SRV_A_OUT"),
    ("R45", "1", "SRV_A_REF"), ("R45", "2", "SIG_GND"),
    ("R46", "1", "SRV_A_OUT"), ("R46", "2", "SRV_B_IN"),
    ("U2B", "IN-", "SRV_B_IN"), ("U2B", "IN+", "SRV_B_REF"),
    ("U2B", "OUT", "SRV_B_OUT"),
    ("R47", "1", "SRV_B_IN"), ("R47", "2", "SRV_B_OUT"),
    ("C16", "1", "SRV_B_IN"), ("C16", "2", "SRV_B_OUT"),
    ("R49", "1", "SRV_B_REF"), ("R49", "2", "SIG_GND"),
    ("R48", "1", "SRV_B_OUT"), ("R48", "2", "FB"),
    ("U2P", "V+", "VCC_15"), ("U2P", "V-", "VEE_15"),
    ("C17", "1", "VCC_15"), ("C17", "2", "SIG_GND"),
    ("C18", "1", "VEE_15"), ("C18", "2", "SIG_GND"),

    # sensing
    ("R43", "1", "OUT_STAR"), ("R43", "2", "DC_SENSE"),
    ("R50", "1", "Q12_E"), ("R50", "2", "I_SENSE"),

    # local decoupling
    ("C19", "1", "VCC_MAIN"), ("C19", "2", "PWR_GND"),
    ("C20", "2", "VEE_MAIN"), ("C20", "1", "PWR_GND"),
    ("C21", "1", "VCC_MAIN"), ("C21", "2", "PWR_GND"),
    ("C22", "1", "VEE_MAIN"), ("C22", "2", "PWR_GND"),
    ("C23", "1", "VCC_FE"), ("C23", "2", "SIG_GND"),
    ("C24", "1", "VEE_FE"), ("C24", "2", "SIG_GND"),
    ("C25", "1", "VCC_FE"), ("C25", "2", "SIG_GND"),
    ("C26", "1", "VEE_FE"), ("C26", "2", "SIG_GND"),
]

# Nets that are legitimately single-pin or externally driven.
ALLOWED_SINGLE_PIN = {"NC_VMID_OUT"}

# Net classes, matching docs/05 section 5.2.
NET_CLASSES = {
    "HV_RAIL_CH": ["VCC_MAIN", "VEE_MAIN"],
    "SPKR_OUT": ["OUT_STAR", "SPK_OUT", "Q12_E", "Q13_E", "Q14_E", "Q15_E", "ZOB"],
    "PWR_GND": ["PWR_GND"],
    "SIG_GND": ["SIG_GND"],
    "FE_RAIL": ["VCC_FE", "VEE_FE"],
    "LV_RAIL": ["VCC_15", "VEE_15"],
    "AUDIO_IN": ["IN_HOT", "IN_COLD", "RX_INP", "RX_INN", "RX", "TRIM_TOP", "TRIM",
                 "AIN", "LTP_INP"],
    "FEEDBACK": ["FB"],
    "BASE_DRIVE": ["PD_N", "PD_P", "DR_N", "DR_P",
                   "Q12_B", "Q13_B", "Q14_B", "Q15_B"],
    "HIZ": ["LC_A", "LC_B", "BIAS_TOP", "BIAS_BOT", "VB_PRE", "Q5_B", "TP_NODE"],
    "SENSE": ["DC_SENSE", "I_SENSE"],
    # Local low-current nodes: emitter tails, references, servo internals. Default
    # width and clearance are adequate; they are listed so that a genuinely
    # unclassified net shows up as a warning.
    "DEFAULT": ["VMID", "MUTE_NODE", "MUTE_CTL", "Q1A_E", "Q1B_E", "TAIL", "TREF",
                "Q2_E", "Q3A_E", "Q3B_E", "Q5_E", "CSREF", "Q6_E",
                "BADJ", "BADJ_L",
                "SRV_A_IN", "SRV_A_REF", "SRV_A_OUT",
                "SRV_B_IN", "SRV_B_REF", "SRV_B_OUT"],
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def build_indexes():
    by_ref = {c.ref: c for c in COMPONENTS}
    nets = defaultdict(list)
    pins_used = defaultdict(set)
    for ref, pin, net in NETLIST:
        nets[net].append((ref, pin))
        pins_used[ref].add(pin)
    return by_ref, nets, pins_used


def check() -> int:
    by_ref, nets, pins_used = build_indexes()
    errors, warnings = [], []

    for ref, pin, net in NETLIST:
        if ref not in by_ref:
            errors.append(f"connection references unknown component {ref}")
        elif pin not in by_ref[ref].pins:
            errors.append(f"{ref} has no pin '{pin}' "
                          f"(declared: {', '.join(by_ref[ref].pins)})")

    for c in COMPONENTS:
        missing = set(c.pins) - pins_used.get(c.ref, set())
        if missing:
            errors.append(f"{c.ref} ({c.value}) has unconnected pins: "
                          f"{', '.join(sorted(missing))}")

    for net, conns in sorted(nets.items()):
        # A hierarchical pin net may legitimately have one internal connection; it
        # gets its second at the parent sheet.
        if len(conns) < 2 and net not in ALLOWED_SINGLE_PIN and net not in HIER_PINS:
            errors.append(f"net '{net}' has only one connection: {conns}")

    dupes = defaultdict(list)
    for ref, pin, net in NETLIST:
        dupes[(ref, pin)].append(net)
    for (ref, pin), n in dupes.items():
        if len(n) > 1 and not (ref == "R7"):
            errors.append(f"{ref}.{pin} connected to multiple nets: {n}")

    classed = {n for nl in NET_CLASSES.values() for n in nl}
    for net in nets:
        if net not in classed and net not in ALLOWED_SINGLE_PIN:
            warnings.append(f"net '{net}' has no net class assignment")

    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")
    print()
    print(f"{len(COMPONENTS)} components, {len(nets)} nets, "
          f"{len(NETLIST)} connections")
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


def stats() -> int:
    by_ref, nets, _ = build_indexes()
    kinds = defaultdict(int)
    for c in COMPONENTS:
        kinds[c.ref.rstrip("0123456789ABP")] += 1
    print("Per channel:")
    for k in sorted(kinds):
        print(f"  {k or '?':<4} {kinds[k]:>3}")
    dnp = [c.ref for c in COMPONENTS if c.dnp]
    hs = [c.ref for c in COMPONENTS if c.on_heatsink]
    pkgs = {c.package_of for c in COMPONENTS if c.package_of}
    print(f"\nPhysical parts per channel: "
          f"{len([c for c in COMPONENTS if not c.dnp and not c.package_of]) + len(pkgs)}")
    print(f"Do-not-populate: {', '.join(dnp)}")
    print(f"Heatsink-mounted: {', '.join(hs)}")
    print(f"Multi-section packages: {', '.join(sorted(pkgs))}")
    print(f"\nFor a 3-channel board, multiply by 3 and add the shared "
          f"regulator/protection/PSU-interface sections.")
    print(f"\nLargest nets:")
    for net, conns in sorted(nets.items(), key=lambda kv: -len(kv[1]))[:8]:
        print(f"  {net:<12} {len(conns):>3} connections")
    return 0


def emit_netlist() -> int:
    """KiCad-compatible flat netlist for one channel, for direct Pcbnew import."""
    by_ref, nets, _ = build_indexes()
    print("(export (version D)")
    print("  (components")
    for c in COMPONENTS:
        if c.dnp or c.ref.endswith("P") and c.package_of:
            continue
        print(f'    (comp (ref "{c.ref}") (value "{c.value}") '
              f'(footprint "{c.footprint}"))')
    print("  )")
    print("  (nets")
    for i, (net, conns) in enumerate(sorted(nets.items()), start=1):
        print(f'    (net (code "{i}") (name "{net}")')
        for ref, pin in conns:
            print(f'      (node (ref "{ref}") (pin "{pin}"))')
        print("    )")
    print("  )")
    print(")")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--netlist", action="store_true")
    a = p.parse_args()
    if a.netlist:
        return emit_netlist()
    if a.stats:
        return stats()
    return check()


if __name__ == "__main__":
    sys.exit(main())
