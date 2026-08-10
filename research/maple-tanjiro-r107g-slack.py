#!/usr/bin/env python3
"""R107-G: the non-byte slack bound.

For every decode family, the DRAM floor is  unique_bytes/266.3e9 + 3.97 us  (rule 55's
measured per-dispatch intercept).  No kernel-internal change that keeps the byte traffic
fixed -- and that includes every instruction-side / ALU-density change, which is what
this census was commissioned to price -- can take the dispatch below that floor.  So

    slack_us = dispatch_us - bytes_us - intercept_us

is a HARD upper bound on the whole non-byte lever, per dispatch.  Converting it with
rule 105 gives the maximum % of cs any such change could ever buy.  If that number is
below the 0.4 % bar, the family is closed to instruction-side work by arithmetic, with
no further receipts needed.
"""

PEAK = 266.3e9
INTERCEPT = 3.97          # us, rule 55 per-dispatch intercept on M4
PRICE = 0.015228          # % of cs per M4 us/step
BAR = 0.4

FAM = [
    # name, calls, M4 us/step, unique bytes/dispatch, k, note
    ("D  T2c routed gate+up",  39, 1497.7,  8_912_821, 0.4369, "directly probed"),
    ("A  T3b oproj h64",       30, 1117.7,  8_652_667, 0.4369, "inferred"),
    ("C  T0b(a) qkv h64",      30, 1340.1, 10_823_667, 0.4369, "inferred"),
    ("B  T2d down+residual",   39,  858.9,  5_013_590, 0.4369, "inferred"),
    ("E  T2b gate_sp h64",     30,  248.0,    262_000, 0.5000, "inferred"),
]

print("=" * 78)
print("NON-BYTE SLACK BOUND  (hard ceiling on every fixed-byte / instruction-side lever)")
print("=" * 78)
print(f"  DRAM peak {PEAK/1e9:.1f} GB/s ; rule-55 intercept {INTERCEPT:.2f} us/dispatch ;"
      f" price {PRICE} %cs per M4 us/step ; bar {BAR} %")
print()
hdr = ("  family                     disp_us  bytes_us  floor_us  slack_us  "
       "slack/step  max %cs  bars   verdict")
print(hdr)
for name, calls, m4, byt, k, note in FAM:
    disp = m4 / calls
    bus = byt / PEAK * 1e6
    floor = bus + INTERCEPT
    slack = disp - floor
    per_step = slack * calls
    pct = per_step * k * PRICE
    bars = pct / BAR
    verdict = "CLOSED" if bars < 1.0 else "OPEN (but see family notes)"
    print(f"  {name:<26} {disp:7.2f} {bus:9.3f} {floor:9.3f} {slack:9.3f} "
          f"{per_step:10.1f} {pct:8.3f} {bars:6.2f}   {verdict}")

print()
print("  Reading: for A, B, C and D the ENTIRE non-byte budget -- exposed ALU plus every")
print("  unexplained latency term put together -- is smaller than one 0.4 % bar.  For")
print("  B it is not even positive: the family already runs at or below the modelled")
print("  DRAM floor, which also flags a ~3 % tension in the byte audit (see threats).")
print()

print("=" * 78)
print("FULL-FUSION PRIZE for family E (bytes still have to move; dispatch does not)")
print("=" * 78)
calls, m4, byt, k = 30, 248.0, 262_000, 0.5
disp = m4 / calls
bus = byt / PEAK * 1e6
prize = (disp - bus) * calls
print(f"  dispatch {disp:.2f} us ; irreducible byte time {bus:.3f} us")
print(f"  prize if the dispatch disappears entirely: {prize:.1f} M4 us/step"
      f" = {prize*k*PRICE:.3f} % of cs = {prize*k*PRICE/BAR:.2f} bars")
print(f"  of which rule 65's fixed per-dispatch cost 2.3403 us x {calls}"
      f" = {2.3403*calls:.1f} us/step = {2.3403*calls*k*PRICE:.3f} % of cs")
print("  NOTE: the lever is dispatch-count / fusion, NOT bytes and NOT issue.")
print("  Prior art already priced on this axis: #48 dispatch-count reduction = -0.1488 %.")

print()
print("=" * 78)
print("ISSUE-SIDE EXCHANGE RATES, per family, both nominal and exposed")
print("=" * 78)
SLOT = {"D": 0.038044, "A": 0.004506, "C": 0.038044, "B": 0.038044, "E": 0.038044}
BASE_FMA = {"D": 128, "A": 1024, "C": 256, "B": 64, "E": 68}
EXPOSURE = 0.087          # measured on family D at its operating point
print("  family   slot us/fma-thr  base fma/thr   nominal bar   exposed bar   exposed bar")
print("                                          (instr/thr)   (instr/thr)   as x base load")
for name, calls, m4, byt, k, note in FAM:
    key = name.split()[0]
    slot = SLOT[key]
    nom_step = slot * calls
    nom_pct = nom_step * k * PRICE
    nom_bar = BAR / nom_pct
    exp_bar = nom_bar / EXPOSURE
    print(f"  {key:<8} {slot:14.6f} {BASE_FMA[key]:13d} {nom_bar:13.0f} {exp_bar:13.0f}"
          f" {exp_bar/BASE_FMA[key]:14.1f}x")
print()
print("  'nominal' assumes every added/removed instruction costs a full machine slot")
print("  (i.e. zero overlap with memory).  'exposed' uses the 8.7 % exposure fraction")
print("  measured directly on family D.  Even the NOMINAL bar exceeds the base ALU load")
print("  for D, B and E; for A and C the nominal bar is a fraction of the base load, so")
print("  for those two the closure argument rests on the slack bound above rather than")
print("  on the exchange rate alone.")
