#!/usr/bin/env python3
"""Advisor r103: decompose our ranked receipts with the exact rule-58 identity
D = 4P + T, where D = cand_dec (decode us/step), P = prefill us/token and
T is the true steady-state per-step time.

The identity is EXACT BY CONSTRUCTION of the trusted harness arithmetic
(decode_seconds_per_token = (S + 128*T)/128 with S = 512*P), confirmed in
research/frieren-r97-rule58-result.md. It is not a regression fit, so T is
computed exactly for every receipt from two published fields.
"""
import math

X = -5.1831677111  # ln cs = X - 0.75 ln cand_dec - 0.25 ln cand_pre (SI units)

# name: (cs, cand_dec us/step, cand_pre us/tok, receipt)
ROWS = {
    "rank1  ": (2.590559, 4894.114, 187.637, "25e1f18e"),
    "armR   ": (2.589321, 4893.712, 188.043, "7ce1262d"),
    "rank3  ": (2.588750, 4898.929, 187.608, "83fd2642"),
    "rank4  ": (2.587191, 4900.524, 187.877, "05dd8bbf"),
    "front  ": (2.582286, 4913.117, 187.857, "e08d759f"),
    "ctrl   ": (2.575633, 4925.255, 188.405, "59bd72a3"),
}


def cs_of(D_us, P_us):
    return math.exp(X - 0.75 * math.log(D_us / 1e6) - 0.25 * math.log(P_us / 1e6))


print("name     receipt    cs         D          P         4P         T=D-4P    cs check")
for k, (cs, D, P, r) in ROWS.items():
    print(f"{k} {r}  {cs:.6f} {D:9.3f} {P:8.3f} {4*P:9.3f} {D-4*P:10.3f}  {cs_of(D,P):.6f}")

cs_a, D_a, P_a, _ = ROWS["armR   "]
cs_f, D_f, P_f, _ = ROWS["front  "]
T_a, T_f = D_a - 4 * P_a, D_f - 4 * P_f

print()
print("frontier minus Arm R")
print(f"  dD  (whole-step decode, what receipts show) = {D_f-D_a:+8.3f} us/step")
print(f"  d4P (amortised seed prefill inside D)       = {4*P_f-4*P_a:+8.3f} us/step")
print(f"  dT  (TRUE steady-state per-step regression) = {T_f-T_a:+8.3f} us/step")

dec = -0.75 * (math.log(D_f) - math.log(D_a))
pre = -0.25 * (math.log(P_f) - math.log(P_a))
print()
print("cs decomposition (frontier vs Arm R)")
print(f"  decode  term  = {dec*100:+.4f} %")
print(f"  prefill term  = {pre*100:+.4f} %")
print(f"  net           = {(dec+pre)*100:+.4f} %   actual = {math.log(cs_f/cs_a)*100:+.4f} %")

# The prize: restore T to Arm R's level while KEEPING the frontier's better prefill.
D_new = T_a + 4 * P_f
cs_new = cs_of(D_new, P_f)
print()
print("prize if T is fully restored and the frontier prefill is kept")
print(f"  D  = {D_new:.3f} us/step   cs = {cs_new:.6f}")
print(f"  vs frontier {cs_f:.6f}  ->  {(cs_new/cs_f-1)*100:+.4f} %")
print(f"  vs Arm R    {cs_a:.6f}  ->  {(cs_new/cs_a-1)*100:+.4f} %")
