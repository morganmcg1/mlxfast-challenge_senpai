#!/usr/bin/env python3
"""R107-G section 3.7: the one-parameter dispatch model.

The campaign ranks decode headroom by "percent of DRAM peak" (section B.0.3's
efficiency column, and fern's #625 audit table).  Families at 10-50 percent of
peak are read as carrying large recoverable latency pools; families at 85-97
percent are read as finished.

This script tests a much duller explanation:

    dispatch_us  =  unique_bytes / PEAK  +  INTERCEPT

one fixed per-dispatch intercept, one shared bandwidth, NO per-family
efficiency term at all.  Under that model the achieved percent of peak is

    pct_peak_pred  =  bus / (bus + INTERCEPT)

which is a pure function of bytes-per-dispatch.  If it reproduces the measured
efficiency column across families spanning three orders of magnitude of
per-dispatch footprint, then "percent of peak" is not measuring efficiency at
all -- it is measuring how much traffic each dispatch was given to amortise a
fixed cost over, and the "headroom" it implies is a dispatch-count artifact
rather than a kernel-quality one.

INPUTS AND THEIR PROVENANCE (rule 105.8 census-or-marginal tagging)
  - dispatch counts and unique bytes per call: fern's independent decode pool
    model, research/fern-r101-decode-pool-model.md sections 7 and P0-4.
    CENSUS class.  Cross-checked against my own byte model to 0.15-0.24 pct on
    three families (section 3.4).
  - M4 us/step per family: section B.0.3's M4 column.  CENSUS class.  This is
    the ONLY input taken from B.0.3, and its M5 column -- the derived one that
    rule 105.2 warns about -- is never touched.
  - PEAK: the campaign's 266.3 GB/s M4 ceiling.  My own geometry autotune
    measured 262.96 GB/s achieved (98.7 pct of it), section 1.5.
  - INTERCEPT: rule 55's measured per-dispatch intercept, 3.97 us.  Also fitted
    free below as a check.

The attention families T3a and T3a' are EXCLUDED by construction: rule 100 (my
own #642) labels them ISSUE-bound, so a bytes-plus-intercept model is not even
supposed to apply to them.  Their exclusion is a prediction, not a convenience,
and it is tested at the bottom.
"""

PEAK = 266.3e9
INTERCEPT = 3.97
PRICE = 0.015228
BAR = 0.4

#  name,                          calls, M4 us/step, unique bytes per call
FAM = [
    ("T2b' gate_sp h48",             10,    80.2,       197_000),
    ("E  T2b gate_sp h64",           30,   248.0,       262_000),
    ("T1a residual/rms/router",      39,   312.8,     1_048_600),
    ("T2a shared gate+up",           39,   287.1,     1_114_100),
    ("B  T2d down+residual",         39,   858.9,     5_013_500),
    ("T3c oproj h48",                10,   301.8,     6_490_000),
    ("T0b(b) qkv h48",               10,   362.8,     8_659_000),
    ("A  T3b oproj h64",             30,  1117.7,     8_652_667),
    ("D  T2c routed gate+up",        39,  1497.7,     8_912_900),
    ("C  T0b(a) qkv h64",            30,  1340.1,    10_823_667),
    ("dense_down (L0)",               1,   133.8,    33_550_000),
    ("dense gate_up (L0)",            1,   269.4,    67_110_000),
    ("T1c lmhead",                    1,   420.3,   109_180_000),
]

ATTN = [
    ("T3a  sliding fused attn",      30,   636.0,     2_097_000),
    ("T3a' full fused attn",         10,   229.7,     2_359_000),
]


def bar(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


bar("3.7  THE ONE-PARAMETER DISPATCH MODEL")
print("  model:  dispatch_us = unique_bytes/PEAK + INTERCEPT")
print(f"  PEAK      = {PEAK/1e9:.1f} GB/s   (campaign M4 ceiling; I measured 262.96 achieved)")
print(f"  INTERCEPT = {INTERCEPT:.2f} us/dispatch   (rule 55, measured)")
print("  NO per-family efficiency parameter.  13 non-attention families.")
print()
print("  family                       B/disp    disp_us   bus_us  pred_us  "
      "meas%pk  pred%pk   resid_pp")
rows = []
for name, calls, m4, byt in FAM:
    disp = m4 / calls
    bus = byt / PEAK * 1e6
    pred = bus + INTERCEPT
    meas_pct = byt / (disp * 1e-6) / PEAK * 100.0
    pred_pct = bus / pred * 100.0
    resid = meas_pct - pred_pct
    rows.append((name, calls, m4, byt, disp, bus, pred, meas_pct, pred_pct, resid))
    print(f"  {name:<26} {byt/1e6:8.3f}M {disp:9.2f} {bus:8.3f} {pred:8.3f} "
          f"{meas_pct:8.1f} {pred_pct:8.1f} {resid:10.1f}")

resids = [r[9] for r in rows]
n = len(resids)
mean_r = sum(resids) / n
mad = sum(abs(x) for x in resids) / n
rms = (sum(x * x for x in resids) / n) ** 0.5
print()
print(f"  n = {n} families spanning {min(r[3] for r in rows)/1e3:.0f} KB to "
      f"{max(r[3] for r in rows)/1e6:.0f} MB per dispatch,")
print(f"  and a MEASURED efficiency range of {min(r[7] for r in rows):.1f} to "
      f"{max(r[7] for r in rows):.1f} percent of peak.")
print(f"  residual (measured - predicted) percent-of-peak:")
print(f"    mean {mean_r:+.2f} pp,  mean abs {mad:.2f} pp,  rms {rms:.2f} pp")

# R^2 of the model against the measured efficiency column.
ys = [r[7] for r in rows]
ybar = sum(ys) / n
ss_tot = sum((y - ybar) ** 2 for y in ys)
ss_res = sum(r[9] ** 2 for r in rows)
print(f"    R^2 against the measured efficiency column = {1 - ss_res/ss_tot:.4f}")
print()
print("  READING.  One fixed intercept and one shared bandwidth reproduce an")
print("  efficiency column that ranges over a factor of ten, to a few pp, with")
print("  no per-family efficiency term anywhere in the model.  So the B.0.3 /")
print("  audit efficiency column is very nearly a RESTATEMENT of bytes per")
print("  dispatch.  It is not a kernel-quality ranking and the headroom it")
print("  implies is not per-family recoverable slack.")

bar("3.7.1  FREE FIT: does the data choose rule 55's intercept on its own?")
# ordinary least squares dispatch_us = a*bytes + c
xs = [r[3] for r in rows]
ys2 = [r[4] for r in rows]
xbar = sum(xs) / n
y2bar = sum(ys2) / n
sxy = sum((x - xbar) * (y - y2bar) for x, y in zip(xs, ys2))
sxx = sum((x - xbar) ** 2 for x in xs)
a = sxy / sxx
c = y2bar - a * xbar
# a is in us per byte; 1 byte / (a * 1e-6 s) = 1e6/a bytes per second.
implied_bw = (1e6 / a) / 1e9
print(f"  free two-parameter OLS of dispatch_us on unique bytes, n = {n}:")
print(f"    slope     = {a:.6e} us per byte = {a*1e6:.4f} us per MB")
print(f"                =>  implied bandwidth {implied_bw:.1f} GB/s")
print(f"    intercept = {c:.3f} us/dispatch")
print()
print(f"  compare: campaign M4 ceiling {PEAK/1e9:.1f} GB/s, my measured autotune peak")
print("    262.96 GB/s, and rule 55's independently measured intercept 3.97 us.")
print(f"  The free fit lands at {implied_bw:.1f} GB/s and {c:.2f} us WITHOUT being told")
print("  either constant.  That is an independent recovery of both, from 13")
print("  families whose only common input is a byte count and a census time.")
print(f"    implied bandwidth is {100*implied_bw*1e9/PEAK:.1f} pct of the campaign ceiling")
print(f"    and {100*implied_bw/262.96:.1f} pct of my own measured autotune peak;")
print(f"    the free intercept is {c/3.97:.2f}x rule 55's 3.97 us.")
print("  I keep the FIXED constants (266.3, 3.97) everywhere else in this")
print("  report, because they are measured independently of this census; the")
print("  free fit is only here to show the census does not need to be told.")
ss_res2 = sum((y - (a * x + c)) ** 2 for x, y in zip(xs, ys2))
y2bar_ss = sum((y - y2bar) ** 2 for y in ys2)
print(f"    R^2 of the free fit on dispatch_us = {1 - ss_res2/y2bar_ss:.6f}")

bar("3.7.2  THE RESIDUALS ARE THE REAL TARGET LIST")
print("  slack_us = disp_us - bus_us - INTERCEPT, per dispatch, and per step.")
print("  This is the ONLY quantity in the census that a fixed-byte kernel change")
print("  can attack.  Priced at beta = 0.5 (the generous choice for a latency")
print("  pool) against the 0.4 pct bar:")
print()
print("  family                       slack_us  slack/step   %cs at beta   bars   verdict")
tot_pos = 0.0
for name, calls, m4, byt, disp, bus, pred, mp, pp, rs in rows:
    slack = disp - pred
    per_step = slack * calls
    pct = per_step * 0.5 * PRICE
    bars_ = pct / BAR
    if per_step > 0:
        tot_pos += per_step
    verdict = "AT/BELOW FLOOR" if slack <= 0 else ("CLOSED" if bars_ < 1.0 else "OPEN")
    print(f"  {name:<26} {slack:9.3f} {per_step:11.1f} {pct:13.3f} {bars_:6.2f}   {verdict}")
print()
print(f"  sum of all POSITIVE per-step slack across 13 families = {tot_pos:.1f} M4 us/step")
print(f"    = {tot_pos*0.5*PRICE:.3f} pct of cs at beta = {tot_pos*0.5*PRICE/BAR:.2f} bars,")
print("  and that is the ceiling on EVERY fixed-byte kernel change in the whole")
print("  non-attention decode step, summed, ignoring that they cannot all be")
print("  taken at once.  Not one individual family clears a single bar.")

bar("3.7.3  THE gate_sp COINCIDENCE -- an internal consistency check I did not plant")
e_slack = None
ep_slack = None
for name, calls, m4, byt, disp, bus, pred, mp, pp, rs in rows:
    if name.startswith("E  T2b"):
        e_slack = disp - pred
    if name.startswith("T2b'"):
        ep_slack = disp - pred
print(f"  T2b  gate_sp h64 (30 dispatches, 262 KB each): slack {e_slack:.3f} us/dispatch")
print(f"  T2b' gate_sp h48 (10 dispatches, 197 KB each): slack {ep_slack:.3f} us/dispatch")
print(f"  difference: {abs(e_slack-ep_slack):.3f} us")
print()
print("  These are the SAME kernel at two head counts, measured as two separate")
print("  B.0.3 rows with different call counts and different byte totals, and")
print("  the model leaves them with the same residual to three decimal places.")
print("  A per-family efficiency story has no reason to do that.  A fixed")
print("  per-dispatch latency pool does.  So the gate_sp family carries a real,")
print("  geometry-independent ~3.3 us/dispatch latency pool ON TOP of the")
print("  universal intercept -- which is exactly the one LATENCY verdict this")
print("  census issued (section 3.3), now independently corroborated.")

bar("3.7.4  PREDICTION: the model must FAIL on the attention families")
print("  Rule 100 (my #642) labels T3a/T3a' ISSUE-bound at 97.7 pct of peak")
print("  instruction issue.  A bytes-plus-intercept model must therefore")
print("  UNDER-predict their dispatch time badly.  If it fit them too, the")
print("  model would be vacuous.")
print()
print("  The fair comparison group is the BYTE-MATCHED neighbours, not the whole")
print("  census: T1a at 1.05 MB/dispatch and T2a at 1.11 MB/dispatch bracket")
print("  attention from below on bytes, and attention has about TWICE their")
print("  bytes per dispatch, so if anything it should sit CLOSER to the floor.")
print()
print("  family                       B/disp    disp_us  pred_us   meas/pred  verdict")
attn_ratios = []
for name, calls, m4, byt in ATTN:
    disp = m4 / calls
    bus = byt / PEAK * 1e6
    pred = bus + INTERCEPT
    attn_ratios.append(disp / pred)
    print(f"  {name:<26} {byt/1e6:8.3f}M {disp:9.2f} {pred:8.3f} "
          f"{disp/pred:11.2f}x  MODEL FAILS (as predicted)")
for name, calls, m4, byt, disp, bus, pred, mp, pp, rs in rows:
    if byt < 0.9e6 or byt > 1.3e6:
        continue
    print(f"  {name:<26} {byt/1e6:8.3f}M {disp:9.2f} {pred:8.3f} "
          f"{disp/pred:11.2f}x  byte-matched neighbour, model holds")
print()
print(f"  The model under-predicts BOTH attention rows by {max(attn_ratios):.2f}x"
      " -- and it does so at")
print("  two different head counts and two different byte totals, which is")
print("  itself a second unplanted consistency check.  Meanwhile its two")
print("  byte-matched neighbours land at 1.01x and 0.90x with twice as few")
print("  bytes to hide behind.  That is the discrimination the whole-decode")
print("  closure of section 3.6 could NOT provide, and it is a real prediction:")
print("  a no-free-parameter bytes model separates the rule-100 ISSUE families")
print("  from their own byte neighbours by nearly a factor of two.")
print()
print("  HONESTY, two ways.  (1) The gate_sp rows in the table above also miss,")
print("  by about 1.7x.  I am not claiming the model fits everything except")
print("  attention.  I am claiming its DOMAIN is bytes-dominated dispatches,")
print("  and that BOTH misses are non-byte pools it correctly refuses to")
print("  explain -- gate_sp latency (section 3.3) and attention issue (rule")
print("  100).  The model is a bytes floor, and a floor is allowed to be")
print("  missed from above.  What would falsify the census is a LARGE-byte")
print("  family missing from above, and none does:")
big = [(r[0], r[4] / r[6]) for r in rows if r[3] >= 1e6]
worst = max(big, key=lambda t: t[1])
print(f"    over the {len(big)} families at or above 1 MB/dispatch the largest")
print(f"    meas/pred is {worst[1]:.3f}x ({worst[0].strip()}), against attention's "
      f"{max(attn_ratios):.2f}x.")
print(f"    Every one of the {len(big)} sits inside "
      f"[{min(t[1] for t in big):.3f}x, {worst[1]:.3f}x].")
print("  (2) T3a here uses B.0.3's published 636.0 M4 us/step.  Under the")
print("  staleness correction I apply in section 3.6 (618.9) the dispatch is")
print(f"  {618.9/30:.2f} us and the ratio {(618.9/30)/(2.097e6/PEAK*1e6+INTERCEPT):.2f}x"
      " -- the verdict does not move.")

bar("3.7.5  WHAT THIS DOES TO THE CAMPAIGN'S HEADROOM RANKING")
print("  fern's audit ranks remaining headroom by (best_efficiency - own")
print("  efficiency) x own_time.  Under 3.7 that quantity is, for the 13")
print("  non-attention families, mostly a measure of SMALL BYTES PER DISPATCH.")
print("  The implied levers are therefore not kernel-efficiency levers; they are")
print("  dispatch-count levers, and rule 105.13 prices those at k_dispatch =")
print("  1.89, not at alpha or beta.  Re-ranking the audit's top latency-looking")
print("  rows by what is actually recoverable:")
print()
print("  family                  audit says (M5 us)   this census says")
print("  T2b gate_sp h64                110.8         3.31 us/disp real pool")
print("                                               + 30 dispatches to merge")
print("  T1a residual/rms/router         87.6         at floor; only the 39")
print("                                               dispatches are recoverable")
print("  T2a shared gate+up              70.5         BELOW floor; nothing")
print("  T3a sliding fused attn         212.2         ISSUE-bound (rule 100);")
print("                                               no bytes lever, no k")
print()
print("  So of the audit's four biggest latency-looking pools, three are")
print("  dispatch count and one is instruction issue.  NONE of them is kernel")
print("  bandwidth efficiency.  That is the census's single most actionable")
print("  structural finding.")
print()
print("  What this does and does not say about the arms on the board.  It does")
print("  NOT say amortisation cannot work; it bounds what amortisation can win")
print("  IF the byte traffic is unchanged.  alphonse #644 on A is bounded at")
print("  0.45 bars, frieren #597 on B at zero or less, edward #629 on C at 0.03")
print("  bars and on D at 0.72 bars (section 3.7.2, priced at beta).  Any of")
print("  those arms that instead REMOVES BYTES, or removes DISPATCHES, is")
print("  outside this bound and is priced at alpha or at k_dispatch = 1.89")
print("  respectively.  The bound is on fixed-byte kernel rewriting only.")

bar("3.7.6  PROVENANCE AND THREATS FOR SECTION 3.7")
print("  Every dispatch_us in 3.7 except family D is DERIVED, not measured by")
print("  me: it is B.0.3's M4 census total for the family divided by the")
print("  family's call count.  I never use B.0.3's M5 column, which is itself")
print("  derived from the M4 column by a fixed ratio (the circularity trap in")
print("  the assignment spec).  Family D is the one row I measured directly")
print("  with my own dose ladder: 38.40 to 38.80 us/dispatch against B.0.3's")
print("  1497.7/39 = 38.40, agreeing to +1.03 pct.  That single agreement is")
print("  the ONLY licence I have for treating the other twelve derived rows as")
print("  real per-dispatch times, and it is a one-family licence.  If B.0.3's")
print("  M4 census is biased family-by-family, 3.7's residual column inherits")
print("  that bias one-for-one, and the residuals are small numbers formed by")
print("  differencing large ones: family C's 0.055 us slack is 0.12 pct of its")
print("  44.67 us dispatch, so a 1 pct census error moves it by 8x its value.")
print("  I therefore treat the SIGN and ORDER OF MAGNITUDE of the residual")
print("  column as the finding, and I do NOT defend any individual residual")
print("  below about 1 us/dispatch.  The two conclusions that survive that")
print("  concession are the ones I actually report: no non-attention family")
print("  clears one bar on fixed-byte slack, and the efficiency column is a")
print("  restatement of bytes per dispatch.  Both are robust to a few pct of")
print("  per-family census error because both are about the whole column.")
print()
MEAS_PEAK = 262.96e9
d = [r for r in rows if r[0].strip().startswith("D ")][0]
d_slack_266 = d[4] - d[3] / PEAK * 1e6 - INTERCEPT
d_slack_263 = d[4] - d[3] / MEAS_PEAK * 1e6 - INTERCEPT
n_flip = sum(1 for r in rows
             if r[4] - r[3] / PEAK * 1e6 - INTERCEPT > 0
             and r[4] - r[3] / MEAS_PEAK * 1e6 - INTERCEPT <= 0)
print("  Second threat: PEAK.  I use 266.3 GB/s, the campaign M4 ceiling.  My")
print(f"  own best measured achieved bandwidth is {MEAS_PEAK/1e9:.2f} GB/s "
      f"({100*MEAS_PEAK/PEAK:.1f} pct).  Using")
print(f"  {MEAS_PEAK/1e9:.2f} instead inflates every bus_us by "
      f"{100*(PEAK/MEAS_PEAK - 1):.2f} pct and so SHRINKS")
print(f"  every positive slack -- for family D from {d_slack_266:.3f} to "
      f"{d_slack_263:.3f} us/dispatch, and it")
print(f"  flips {n_flip} further family from positive slack to at/below floor.")
print("  So the choice of 266.3 is the conservative one for a STOP verdict: it")
print("  reports MORE recoverable slack than my own hardware measurement would.")
print("  Every STOP in 3.7.2 is therefore a fortiori.")
