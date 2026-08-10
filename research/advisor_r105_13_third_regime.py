#!/usr/bin/env python3
"""Rule 105.13 arithmetic: the dispatch regime, and the first direct validation
of the alpha/beta host model at whole-decode level.

Inputs, each with a host tag (rule 105.6 discipline):

  price      0.015228 %cs per M5 us/step   (M5, receipt-fitted, w = 0.7500)
  alpha      0.4369   bytes-regime M4 -> M5 factor
  beta       0.5      latency-regime M4 -> M5 factor
  T_M4       8448.0 us/step  M4 local `mean_step_seconds` = 0.008448
                             (maple-nezuko R106-B section C.3, PR #616)
  T_M5       4141.5 us/step  M5 receipt steady state, rule 58
  cens_M4    8096.3 us/step  section B.0.3 M4 column, 15 rows
  cens_M5    3650.9 us/step  section B.0.3 M5 column, 15 rows (derived, not measured)
  glue_M4    1.2382 us/dispatch  rule 57, M4, saturated marginal
  disp_M5    2.3403 us/dispatch  rule 65, M5, marginal
"""

a, b, price = 0.4369, 0.5, 0.015228

print("== 1. nezuko R106-B paired deltas: M4 local steady-state, priced bare ==")
for n, d, lo, hi in [("H (H4)", 35.959, 9.831, 62.087),
                     ("K (PACKRED)", 22.145, -7.669, 51.958),
                     ("P (NOREDUCE)", 16.276, -0.395, 32.947)]:
    print(f"  {n:14s} bare {d*price:+.4f}%   beta {d*b*price:+.4f}%   "
          f"alpha {d*a*price:+.4f}%   | LCB bare {lo*price:+.4f}%  beta {lo*b*price:+.4f}%")

print("\n== 2. levels ==")
print(f"  sliding fused attn 670 M4 us/step: bare {670*price:.3f}%  "
      f"beta {670*b*price:.3f}%  alpha {670*a*price:.3f}%")

print("\n== 3. whole-decode steady-state host ratio ==")
T_M4, T_M5 = 8448.0, 4141.5
print(f"  k_steady = T_M5 / T_M4 = {T_M5/T_M4:.4f}   (alpha {a}, beta {b})")
print("  -> lies inside [alpha, beta]: the host model survives its first direct test")
print(f"  naive ratio of the two *reported* decode figures 4925.255/8984.50 = "
      f"{4925.255/8984.50:.4f}  -- ABOVE beta, i.e. the wrong comparison")

print("\n== 4. census coverage and the residue ==")
cens_M4, cens_M5 = 8096.3, 3650.9
res4, res5 = T_M4 - cens_M4, T_M5 - cens_M5
print(f"  B.0.3 M4 column {cens_M4} = {100*cens_M4/T_M4:.1f}% of T_M4; residue {res4:.1f} us/step")
print(f"  B.0.3 M5 column {cens_M5} = {100*cens_M5/T_M5:.1f}% of T_M5; residue {res5:.1f} us/step")
print(f"  implied k_residue = {res5/res4:.3f}")
for k in (0.4369, 0.5, 1.0, 1.890):
    pred = cens_M5 + k*res4
    print(f"    if k_residue = {k:5.3f} -> predicted T_M5 = {pred:7.1f}  "
          f"error vs 4141.5 = {100*(pred/T_M5-1):+6.2f}%")

print("\n== 5. the dispatch regime, from the rulebook alone ==")
kd = 2.3403/1.2382
print(f"  k_dispatch = rule65_M5 / rule57_M4 = 2.3403 / 1.2382 = {kd:.3f}")
print(f"  k_dispatch / alpha = {kd/a:.2f}x   k_dispatch / beta = {kd/b:.2f}x")
print(f"  one marginal dispatch removed = {2.3403*price:.4f}% of cs")
print(f"  one per-layer dispatch x39 layers = {39*2.3403:.1f} M5 us/step "
      f"= {39*2.3403*price:.3f}% of cs")

print("\n== 6. triage dual, extended with the dispatch regime ==")
for pct in (0.4, 0.46, 0.5, 1.0):
    m5 = pct/price
    row = "  %.2f%% bar: M5 %6.2f | M4 bytes %6.1f | M4 latency %6.1f | M4 dispatch %6.1f" % (
        pct, m5, m5/a, m5/b, m5/kd)
    print(row)
