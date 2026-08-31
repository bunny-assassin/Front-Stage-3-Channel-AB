* ============================================================================
* Common FS-3W testbench elements.
*
* The including deck must define these params first:
*   rload  load resistance, ohm
*   cload  load capacitance, F (use 1p for "none"; 0 is not legal)
*   rsrc   Thevenin source impedance at AIN, ohm
*
* and must supply its own source (Vin, node SRC) and its own closure between
* FB and Q1B_B, because the loop-gain deck opens that connection.
* ============================================================================

* Source impedance seen by the LTP. This is not decoration: with a BJT input
* stage the base current through this resistance is the dominant offset term,
* and the worst case at the RV1 wiper is about 2.5 k. Getting it right is the
* difference between the servo having easy work and hard work.
Rsrc   SRC AIN {rsrc}

Rload  SPK_OUT 0 {rload}
Cload  SPK_OUT 0 {cload}

* DC path around the servo integrator. C15 is an open circuit in .op and .ac,
* which leaves U2A as an infinite-gain DC integrator with no feedback and an
* undefined operating point. This resistor restores a finite DC gain of
* 1G/470k = 2128, which is high enough that the servo still nulls the output to
* microvolts, but low enough that SPICE can solve it. Its time constant with
* C15 is 2200 s, so it is invisible in .tran.
Rleak  SRV_A_IN SRV_A_OUT 1G
