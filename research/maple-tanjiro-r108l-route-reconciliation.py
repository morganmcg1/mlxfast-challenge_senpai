#!/usr/bin/env python3
"""R108-L route reconciliation: A (rule 65) vs B (advisor prize) vs C (my slack bars).

Answers advisor comments 5242807697 and 5242969214:
  1. the exact arithmetic, inputs, k and basis behind "1.89 bars";
  2. whether routes B and C are rivals or addends;
  3. whether 105.16 and 105.17 use the same byte floor, and what the
     claimed 4.86x disagreement actually is.

Every constant below is copied unchanged from the committed census
research/maple-tanjiro-r107g-slack.py.  Research-only: reads nothing from the
scored surface and writes nothing.
"""

# ---- pricing constants (rule 55 census fit, M4 Pro applegpu_g16s) -------------
PEAK = 266.3e9        # B/s, measured M4 Pro peak achievable read bandwidth
INTERCEPT = 3.97      # M4 us, rule 55 fitted per-dispatch overhead
PRICE = 0.015228      # %cs per M5 us/step
BAR = 0.4             # %cs per bar

# ---- rule 65: marginal cost of ADDING one dependent dispatch -----------------
RULE65_M5_US = 2.3403   # already M5 us/dispatch -- do NOT multiply by k

# ---- the five census families: name, calls, M4 us/step, uniqueB/dispatch, k ---
FAM = [
    ("D  T2c routed gate+up",  39, 1497.7,  8_912_821, 0.4369),
    ("A  T3b oproj h64",       30, 1117.7,  8_652_667, 0.4369),
    ("C  T0b(a) qkv h64",      30, 1340.1, 10_823_667, 0.4369),
    ("B  T2d down+residual",   39,  858.9,  5_013_590, 0.4369),
    ("E  T2b gate_sp h64",     30,  248.0,    262_000, 0.5000),
]
TOTAL_DISPATCHES = sum(f[1] for f in FAM)   # == 168, the per-layer population

# advisor's 105.23(e) bars, for side-by-side comparison
ADVISOR_BARS = {"D": 0.71, "A": 0.45, "C": None, "B": 0.00, "E": 1.89}


def routes(calls, m4, byt, k):
    """Return every route for one family, in %cs."""
    disp = m4 / calls                       # M4 us per dispatch
    byte = byt / PEAK * 1e6                 # M4 us of unavoidable read time
    slack = disp - byte - INTERCEPT         # M4 us above the modelled floor
    routeC = slack * calls * k * PRICE      # above-floor slack only
    intercept = INTERCEPT * calls * k * PRICE
    routeB = (slack + INTERCEPT) * calls * k * PRICE
    routeA = calls * RULE65_M5_US * PRICE   # rule 65 is M5-native, no k
    return disp, byte, slack, routeC, intercept, routeB, routeA


print("=" * 78)
print("1. EXACT ARITHMETIC BEHIND '1.89 BARS'  (family E, T2b gate_sp h64)")
print("=" * 78)
name, calls, m4, byt, k = FAM[4]
disp, byte, slack, rC, ipct, rB, rA = routes(calls, m4, byt, k)
print(f"  inputs               : calls={calls}, occupancy={m4:.1f} M4 us/step,")
print(f"                         uniqueB/dispatch={byt}, k={k}")
print(f"  disp   = occ/calls   = {m4:.1f}/{calls} = {disp:.4f} M4 us/dispatch")
print(f"  byte   = uniqueB/PEAK= {byt}/{PEAK:.4g} = {byte:.4f} M4 us")
print(f"  floor  = byte+intercept = {byte:.4f} + {INTERCEPT:.4f} = {byte+INTERCEPT:.4f}")
print(f"  slack  = disp-floor  = {disp:.4f} - {byte+INTERCEPT:.4f} = {slack:.4f} M4 us")
print(f"  x calls              = {slack*calls:.2f} M4 us/step")
print(f"  x k x PRICE          = {slack*calls:.2f} x {k} x {PRICE} = {rC:.4f} %cs")
print(f"  / BAR({BAR})          = {rC/BAR:.3f} bars   <-- the '1.89 bars'")
print()
print("  BASIS: slack is occupancy ABOVE a floor that ALREADY CONCEDES the")
print("  per-dispatch intercept.  It bounds fixed-dispatch-count (instruction-")
print("  side) work only -- exactly the question R107-G was commissioned to")
print("  answer.  It was never a ceiling on REMOVING the dispatch.")
print(f"  k={k} here (not 0.4369) because family E was transferred at beta;")
print("  the other four families carry the directly-probed k=0.4369.")
print()

print("=" * 78)
print("2. ADDITIVITY: is route B a RIVAL of route C, or C + intercept?")
print("=" * 78)
hdr = (f"  {'family':<26}{'C %':>9}{'int %':>9}{'C+int %':>10}"
       f"{'B %':>9}{'resid':>9}{'A %':>9}")
print(hdr)
print("  " + "-" * (len(hdr) - 2))
tot = dict(c=0.0, i=0.0, b=0.0, a=0.0)
for name, calls, m4, byt, k in FAM:
    _, _, _, rC, ipct, rB, rA = routes(calls, m4, byt, k)
    tot["c"] += rC; tot["i"] += ipct; tot["b"] += rB; tot["a"] += rA
    print(f"  {name:<26}{rC:>9.4f}{ipct:>9.4f}{rC+ipct:>10.4f}"
          f"{rB:>9.4f}{rB-(rC+ipct):>9.4f}{rA:>9.4f}")
print("  " + "-" * (len(hdr) - 2))
print(f"  {'SUM (168 dispatches)':<26}{tot['c']:>9.4f}{tot['i']:>9.4f}"
      f"{tot['c']+tot['i']:>10.4f}{tot['b']:>9.4f}"
      f"{tot['b']-tot['c']-tot['i']:>9.4f}{tot['a']:>9.4f}")
print()
print("  Residual is identically 0.0000 for every family: route B IS route C")
print("  plus the conceded intercept.  B and C are ADDENDS, not rivals.")
print("  R107-G already printed route B for family E directly:")
name, calls, m4, byt, k = FAM[4]
disp, byte, slack, rC, ipct, rB, rA = routes(calls, m4, byt, k)
print(f"    ({slack:.4f}+{INTERCEPT:.4f}) x {calls} = {(slack+INTERCEPT)*calls:.1f}"
      f" M4 us/step = {rB:.3f} % = {rB/BAR:.2f} bars")
print("  which reproduces the advisor's route B (1.69-1.78 %) to 2-7 %.")
print()
print(f"  And over the whole population routes A and B agree to"
      f" {tot['a']/tot['b']:.3f}x ({abs(tot['a']/tot['b']-1)*100:.0f} %):")
print(f"    route A (rule 65, dispatch-count)  = {tot['a']:.3f} %cs")
print(f"    route B (slack + intercept)        = {tot['b']:.3f} %cs")
print("  Three routes, two instruments, one number.  Nothing is in conflict.")
print()

print("=" * 78)
print("3. THE CLAIMED 4.86x DISAGREEMENT (105.16 vs 105.17)")
print("=" * 78)
print(f"  The five families' calls sum to {TOTAL_DISPATCHES}: they ARE 105.17's")
print("  'all 168 per-layer dispatches'.  Same population.  So the 4.86x cannot")
print("  be a population difference -- it is a QUANTITY difference:")
print()
print(f"    105.16  = above-floor SLACK only              = {tot['c']:.3f} %cs"
      f"  ({tot['c']/BAR:.2f} bars)")
print(f"    intercept addend 105.16 explicitly conceded   = {tot['i']:.3f} %cs")
print(f"    sum (= route B)                               = {tot['b']:.3f} %cs")
print(f"    105.17  = rule 65 over the same 168 dispatches= {tot['a']:.3f} %cs"
      f"   <- 105.17's 5.987 %")
print()
print("  4.86x = 5.987/1.232 divides the TOTAL by one of its two ADDENDS.")
print("  105.16 prices what is above the floor; 105.17 prices the floor itself.")
print(f"  Once the conceded intercept is put back, the two agree to"
      f" {tot['a']/tot['b']:.3f}x.")
print()
print("  Cross-check on the per-dispatch overhead, two independent instruments:")
for lab, kk in (("k=0.4369 (probed)", 0.4369), ("k=0.5000 (beta)", 0.5)):
    print(f"    rule 55 intercept @ {lab:<18} = {INTERCEPT*kk:.4f} M5 us/dispatch"
          f"  -> ratio to rule 65 = {RULE65_M5_US/(INTERCEPT*kk):.3f}x")
print(f"    rule 65 marginal                       = {RULE65_M5_US:.4f} M5 us/dispatch")
print()
print("  BYTE FLOOR, side by side -- the advisor's direct question:")
print(f"    105.16 : YES, my census byte floor.  PEAK={PEAK:.4g} B/s, subtracted")
print("             per dispatch as uniqueB/PEAK, i.e. 2.5272e-08 %cs per byte.")
print("             105.16's numbers were derived FROM that census.")
print("    105.17 : NO byte floor whatsoever.  Pure dispatch-count x rule 65's")
print("             marginal price.  Bandwidth never enters the calculation.")
print("    So the two are not two estimates of one quantity under two floors.")
print("    They are two DIFFERENT terms of one decomposition, and only 105.16")
print("    has a byte floor at all.")
print()

print("=" * 78)
print("4. CANONICAL BARS FROM MY OWN CENSUS (correcting 105.23(e))")
print("=" * 78)
print(f"  {'fam':<5}{'mine':>8}{'advisor':>10}")
print("  " + "-" * 21)
raw = floored = 0.0
for name, calls, m4, byt, k in FAM:
    key = name.split()[0]
    _, _, _, rC, *_ = routes(calls, m4, byt, k)
    bars = rC / BAR
    raw += bars
    floored += max(bars, 0.0)
    adv = ADVISOR_BARS[key]
    print(f"  {key:<5}{bars:>8.2f}" + ("" if adv is None else f"{adv:>10.2f}"))
print("  " + "-" * 21)
print(f"  {'SUM':<5}{raw:>8.2f}{3.08:>10.2f}")
print(f"  my sum, B signed   = {raw:.2f} bars = {raw*BAR:.3f} %cs")
print(f"  my sum, B floored  = {floored:.2f} bars = {floored*BAR:.3f} %cs")
print(f"  advisor 105.23(e)  = 3.08 bars = 1.232 %cs"
      f"  -> {(3.08/raw-1)*100:.0f} % high vs signed,"
      f" {(3.08/floored-1)*100:.0f} % high vs floored")
print("  Family C is 0.03 bars, not the blank the advisor left, and family B is")
print("  -0.50 bars, not 0.00: B already runs at/below the modelled floor, which")
print("  is a flag on the byte audit, not a recoverable zero.")
print()

print("=" * 78)
print("5. THE REMOVAL-DIRECTION GAP (why option 3, not option 1 or 2)")
print("=" * 78)
name, calls, m4, byt, k = FAM[4]
disp, byte, *_ = routes(calls, m4, byt, k)
E_recoverable = disp - byte
PR483 = 0.108
print(f"  family E recoverable occupancy = disp - byte = {E_recoverable:.3f}"
      f" M4 us/dispatch")
print(f"  PR #483 marginal REMOVAL       = {PR483:.3f} M4 us,"
      f" CI [-0.221, +0.438]")
print(f"  gap                            = {E_recoverable/PR483:.1f}x")
print()
print("  All of A, B and C are ATTRIBUTED PER-KERNEL OCCUPANCY.  None is a")
print("  removal-direction measurement.  So option 1 (k wrong) and option 2")
print("  (route B wrong) both misdiagnose: the routes agree with each other.")
print()
print("  MECHANISM (Vendor/mlx-swift .../backend/metal/device.cpp):")
print("    :545-548  every MLX compute encoder is MTL::DispatchTypeConcurrent")
print("    :315-349  needs_barrier_ is raised only when a bound buffer aliases")
print("              prev_outputs_ (RAW/WAW) or prev_inputs_ (WAR)")
print("    :363-391  maybeInsertBarrier runs per dispatch, but emits")
print("              memoryBarrier(BarrierScopeBuffers) only when that flag is set")
print("    => independent adjacent dispatches are ALREADY free to overlap.")
print()
print("  CONSEQUENCE -- the ledger's central symmetry:")
print("    the intercept is COLLECTIBLE only where a barrier is actually emitted,")
print("    i.e. at DEPENDENT boundaries (dep_scope != NONE) -- exactly the")
print("    boundaries fusion cannot legally or profitably cross; and the")
print("    boundaries fusion CAN cross (dep_scope == NONE, ledger rows 1/2/4)")
print("    emit no barrier today, so there is no serialisation there to relieve.")
print()
print("  Concurrency alone does not close the 67x gap:")
print(f"    rule 41's non-serialised share bounds overlap at 1/0.763 ="
      f" {1/0.763:.3f}x.")
print("    The residue is fern 0.9.16: decode wall time is set by the CRITICAL")
print("    PATH through the dependency DAG.  Occupancy above that path is free,")
print("    and removing free work buys nothing (#48: -0.1488 %; #483: ~0).")
print()
print("=" * 78)
print("VERDICT: option 3.  Routes A/B/C are mutually consistent attributed-")
print("occupancy quantities that agree to 8 %; the disagreement is between ALL")
print("of them and the removal direction.  N-NO-MERGEABLE-PAIR is unchanged and")
print("now has a mechanical cause, not merely an empirical one.")
print("=" * 78)
