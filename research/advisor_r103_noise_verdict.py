#!/usr/bin/env python3
"""Price the round-103 ladder against the MEASURED identical-code replicate noise."""
import math

# ---- the verified identical-code replicate set (r93 nulls 1..5, 2026-08-09) ----
NULLS = [
    ("25e1f18e", "03:05:07", 2.590559143419936, 4894.114, 187.637),
    ("d11026c9", "03:27:22", 2.575591397660448, 4931.226, 187.734),
    ("05dd8bbf", "04:15:03", 2.5871906993274836, 4900.524, 187.877),
    ("ab6a15a1", "05:05:16", 2.5802029315195205, 4916.141, 188.117),
    ("4fec8e2d", "05:53:49", 2.5820115277861766, 4912.621, 187.994),
]

# ---- the round-103 comparison receipts ----
LADDER = [
    ("7ce1262d ArmR      30f752df", 2.5893213006341584, 4893.712, 188.043),
    ("83fd2642 rank3     6ada66c9", 2.5887498582225588, 4898.929, 187.608),
    ("e08d759f frontier  a4d3b8dc", 2.582286297407117, 4913.117, 187.857),
    ("59bd72a3 control   c6c66344", 2.575633169483906, 4925.255, 188.405),
]


def T(D, P):
    return D - 4.0 * P


def mstd(xs):
    n = len(xs)
    m = sum(xs) / n
    s = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, s


print("=== identical-code replicate quintuplet (r93 nulls 1-5) ===")
for i, t, cs, D, P in NULLS:
    print(f"  {i} {t}  cs={cs:.6f}  D={D:.3f}  P={P:.3f}  T={T(D,P):.3f}")
cs_m, cs_s = mstd([c for _, _, c, _, _ in NULLS])
l_m, l_s = mstd([math.log(c) for _, _, c, _, _ in NULLS])
T_m, T_s = mstd([T(D, P) for _, _, _, D, P in NULLS])
D_m, D_s = mstd([D for _, _, _, D, _ in NULLS])
P_m, P_s = mstd([P for _, _, _, _, P in NULLS])
csmax = max(c for _, _, c, _, _ in NULLS)
csmin = min(c for _, _, c, _, _ in NULLS)
Tmax = max(T(D, P) for _, _, _, D, P in NULLS)
Tmin = min(T(D, P) for _, _, _, D, P in NULLS)
print(f"\n  mean cs = {cs_m:.6f}   sd(ln cs) = {100*l_s:.4f}%")
print(f"  cs range = {csmin:.6f} .. {csmax:.6f}  = {100*math.log(csmax/csmin):.4f}%")
print(f"  mean T  = {T_m:.3f}   sd(T) = {T_s:.3f} us/step   "
      f"range = {Tmax-Tmin:.3f} us/step")
print(f"  mean D  = {D_m:.3f}   sd(D) = {D_s:.3f} us/step")
print(f"  mean P  = {P_m:.3f}   sd(P) = {P_s:.4f} us/tok")

TRIM_T = 12.0788   # pooled over all verified identical-code groups, dof=14
TRIM_CS = 0.1860   # percent
print(f"\n  pooled trimmed estimates (dof=14): sd(T)={TRIM_T} us/step, "
      f"sd(ln cs)={TRIM_CS}%")

print("\n=== round-103 ladder priced against that noise ===")
armR_cs, armR_T = LADDER[0][1], T(LADDER[0][2], LADDER[0][3])
rows = []
for name, cs, D, P in LADDER:
    rows.append((name, cs, D, P, T(D, P)))
    print(f"  {name}  cs={cs:.6f}  D={D:.3f}  P={P:.3f}  T={T(D,P):.3f}")

print("\n  contrast                        dT (us/step)   sigma_diff   z"
      "        dcs(%)    z_cs")
for a, b, label in [(3, 0, "control - ArmR   (revert cost)"),
                    (3, 2, "control - frontier (R1+R2)   "),
                    (2, 0, "frontier - ArmR  (residual)  "),
                    (1, 0, "rank3 - ArmR                 ")]:
    dT = rows[a][4] - rows[b][4]
    dcs = 100 * math.log(rows[b][1] / rows[a][1])
    for sdT, sdcs, tag in ((T_s, 100 * l_s, "quintuplet"), (TRIM_T, TRIM_CS, "pooled    ")):
        sd = sdT * math.sqrt(2)
        sdc = sdcs * math.sqrt(2)
        print(f"  {label} [{tag}] {dT:8.2f}      {sd:6.2f}   "
              f"{dT/sd:5.2f}    {dcs:7.4f}  {dcs/sdc:5.2f}")

print("\n=== winner's-curse correction on our quoted best cs ===")
print(f"  quoted best cs (max of the quintuplet) = {csmax:.6f}")
print(f"  honest point estimate for that tree    = {cs_m:.6f}  "
      f"(mean of 5 identical-code receipts)")
print(f"  inflation of the quoted maximum        = "
      f"{100*math.log(csmax/cs_m):.4f}% of cs")
se = l_s / math.sqrt(len(NULLS))
print(f"  s.e. of that mean                      = {100*se:.4f}% "
      f"=> 95% CI {cs_m*math.exp(-1.96*se):.6f} .. {cs_m*math.exp(1.96*se):.6f}")

print("\n=== how many replicate receipts to resolve the claimed residual? ===")
for target_us in (20.15, 30.10, 9.95):
    for sd in (T_s, TRIM_T):
        n = 2 * (1.96 + 0.84) ** 2 * sd ** 2 / target_us ** 2
        print(f"  detect {target_us:6.2f} us/step at 80% power with sd={sd:5.2f}: "
              f"n = {math.ceil(n)} receipts PER ARM")
