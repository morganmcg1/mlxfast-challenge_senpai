#!/usr/bin/env python3
"""Reproduces every number in the PR47 D2 and D5 preregistrations.

Research-only support. Outside benchmark.json editablePaths; not part of the
challenge runtime. Run: python3 research/tanjiro-pr47-prereg.py
"""
import math

# ---- renormalisation constants (research/tanjiro-pr34-r2-result.md) ----------
ND0, NP0 = 0.013890, 0.0003845
RATE = 0.148620          # d(ns)/ns per ms of T, = 0.75 / D_cand(ms)
CV = 0.00149             # per-family cv on ns, n=3
SQ2 = math.sqrt(2.0)     # cross-session: two independent ns reads

# ---- the two permanent published ranked anchors ------------------------------
CTRL = dict(id="c3ce66ec", n=0, S=97.9496, T=4.28121, bS=190.0278, bT=12.41494,
            d=0.00504644, p=1.913117e-4, ns_pub=2.544360)
P400 = dict(id="0411779d", n=400, S=97.6165, T=5.07320, bS=198.0817, bT=12.37185,
            d=0.00583583, p=1.906572e-4, ns_pub=2.283549)

ns_of = lambda d, p: (ND0 / d) ** 0.75 * (NP0 / p) ** 0.25
# decode-only exact inverse: ns is proportional to nd^0.75 => d = d0*(ns0/ns)^(4/3)
dT_exact = lambda ns, ns0=CTRL["ns_pub"], d0=CTRL["d"]: \
    1000.0 * d0 * ((ns0 / ns) ** (4.0 / 3.0) - 1.0)
dT_lin = lambda ns, ns0=CTRL["ns_pub"]: math.log(ns0 / ns) / RATE
ns_from_dT = lambda dT: ns_of(CTRL["d"] + dT / 1000.0, CTRL["p"])
# sigma(dT) at an operating point: multiplicative cv on ns -> absolute ms on T
sigma_dT = lambda dT: SQ2 * CV * (CTRL["d"] + dT / 1000.0) * 1000.0 * (4.0 / 3.0)

P = print
P("=" * 74)
P("A. anchors: recomputed ns vs published")
for r in (CTRL, P400):
    P("  %-9s n=%3d  ns_recomp=%.6f  ns_pub=%.6f  drift=%.1e"
      % (r["id"], r["n"], ns_of(r["d"], r["p"]), r["ns_pub"],
         abs(ns_of(r["d"], r["p"]) / r["ns_pub"] - 1)))
DT400_PAIRED = (P400["T"] - P400["bT"]) - (CTRL["T"] - CTRL["bT"])
DT400_CAND = P400["T"] - CTRL["T"]
P("  dT(400) paired    = %.5f ms   <-- primary convention" % DT400_PAIRED)
P("  dT(400) cand-only = %.5f ms   (%.1f%% apart)"
  % (DT400_CAND, 100 * (DT400_PAIRED / DT400_CAND - 1)))

P("=" * 74)
P("B. sigma reconciliation, and sigma(dT) growth with dT")
P("  sigma_rel(ns) = sqrt(2)*0.149%%          = %.6f%%" % (100 * SQ2 * CV))
P("  sigma(dT) via rate  = %.3f us" % (SQ2 * CV / RATE * 1000))
P("  sigma(dT) via chain = %.3f us" % (sigma_dT(0.0) * 1000))
P("  sigma(ns) absolute  = %.6f" % (SQ2 * CV * CTRL["ns_pub"]))
for dT in (0.0, 0.209, 0.306, 0.835):
    P("    dT=%.3f ms -> sigma(dT)=%.3f us" % (dT, sigma_dT(dT) * 1000))

P("=" * 74)
P("C. D2 degeneracy family c(k) = 835.09/(400-k), and the n=100 predictions")
for k in (0, 300):
    c = DT400_PAIRED * 1000 / (400 - k)
    dT100 = c * max(0, 100 - k) / 1000
    P("  H_knee%-3d k=%3d c=%.4f us  dT(100)=%.5f ms  ns=%.6f  pool=%.2f%%"
      % (k, k, c, dT100, ns_from_dT(dT100), RATE * 100 * 406 * c / 1000))
NS0, NS300 = ns_from_dT(2.0877 * 100 / 1000), CTRL["ns_pub"]
sg = SQ2 * CV * CTRL["ns_pub"]
P("  separation = %.6f ns = %.2f sigma, %.2f sigma at 3x sigma"
  % (NS300 - NS0, (NS300 - NS0) / sg, (NS300 - NS0) / (3 * sg)))
P("  R1 accept H_knee0   ns in [%.6f, %.6f]" % (NS0 - 3 * sg, NS0 + 3 * sg))
P("  R2 accept H_knee300 ns in [%.6f, %.6f]" % (NS300 - 3 * sg, NS300 + 3 * sg))
P("  R3 gap              ns in (%.6f, %.6f)" % (NS0 + 3 * sg, NS300 - 3 * sg))

P("=" * 74)
P("D. exact vs linearised inverse (why the rate is not usable at large dT)")
for tag, ns, pub in (("0411779d n=400", P400["ns_pub"], DT400_CAND),
                     ("D2 H_knee0", NS0, 0.20877)):
    P("  %-16s ns=%.6f  lin=%.5f  exact=%.5f  ref=%.5f  lin err=%.1f%%"
      % (tag, ns, dT_lin(ns), dT_exact(ns), pub,
         100 * (dT_lin(ns) / dT_exact(ns) - 1)))

P("=" * 74)
P("E. Reading A: what a null at n=100 implies (the interpretation trap)")
P("  %-8s %8s %10s %14s" % ("r", "knee k", "c (us)", "pool %-of-score"))
for r in (0.500, 0.250, 0.125, 0.000):
    k = (100 - 400 * r) / (1 - r)
    c = DT400_PAIRED * 1000 / (400 - k)
    P("  %-8.3f %8.1f %10.4f %14.2f" % (r, k, c, RATE * 100 * 406 * c / 1000))

P("=" * 74)
P("F. D5 unchained n=400: anchors, continuous readout, ratio CI")
DT_C = DT400_PAIRED
scen = [("high anchor (ratio 1.0)", DT_C),
        ("M4 probe ratio 2.729", DT_C / 2.729),
        ("low anchor (0.36 us)", 0.36 * 400 / 1000)]
P("  %-26s %9s %10s %8s %9s %10s" %
  ("scenario", "c_real us", "dT_u ms", "ratio", "pool %", "ns_pred"))
for name, dTu in scen:
    c_real = dTu * 1000 / 400
    P("  %-26s %9.4f %10.5f %8.3f %9.2f %10.6f"
      % (name, c_real, dTu, DT_C / dTu, RATE * 100 * 406 * c_real / 1000,
         ns_from_dT(dTu)))
P("  3-sigma acceptance windows on ns:")
for name, dTu in scen:
    ns = ns_from_dT(dTu)
    P("    %-26s ns=%.6f  window [%.6f, %.6f]"
      % (name, ns, ns - 3 * sg, ns + 3 * sg))
nsM4 = ns_from_dT(DT_C / 2.729)
for name, dTu in (scen[0], scen[2]):
    P("    M4 prediction is %.1f sigma from %s"
      % (abs(nsM4 - ns_from_dT(dTu)) / sg, name))
P("  ratio CI: sigma_rel(ratio) = sqrt((s_u/dT_u)^2 + (s_c/dT_c)^2)")
for name, dTu in scen:
    sr = math.hypot(sigma_dT(dTu) / dTu, sigma_dT(DT_C) / DT_C)
    P("    %-26s dT_u=%.5f  sigma_rel=%.3f%%  ratio=%.3f +-%.3f (1s) +-%.3f (3s)"
      % (name, dTu, 100 * sr, DT_C / dTu, DT_C / dTu * sr, 3 * DT_C / dTu * sr))

P("=" * 74)
P("G. acceptance band at this frontier (AcceptanceBand.swift:34-67)")
for ax, lo, hi, B, act in (("decode", 0.95, 1.02, ND0, CTRL["d"]),
                           ("prefill", 0.95, 1.05, NP0, CTRL["p"])):
    P("  %-8s window [%.8f, %.8f]  control actual %.8f -> %s (%.1f%% below lo)"
      % (ax, lo * B, hi * B, act, "PASS" if lo * B <= act <= hi * B else "FAIL",
         100 * (1 - act / (lo * B))))
d_arm = CTRL["d"] + 0.20877 / 1000
P("  D2 H_knee0 decode actual %.8f -> FAIL by %.1f%%, identical in kind to the"
  % (d_arm, 100 * (1 - d_arm / (0.95 * ND0))))
P("  unchanged control => the band carries zero bits about this experiment.")
P("  binding gates: decode floor %.4f >= 0.95 OK ; prefill floor %.4f >= 0.95 OK"
  % (ND0 / d_arm, NP0 / CTRL["p"]))
