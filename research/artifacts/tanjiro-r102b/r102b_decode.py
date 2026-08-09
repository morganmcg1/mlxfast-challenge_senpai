#!/usr/bin/env python3
"""R102-B P4 addendum: decode-restricted additivity, and which published
statistic (pinned cs vs paired score) actually carries the least noise for a
decode-only change.
"""
import json
import math
import statistics as st
import sys

CORPUS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r102b-receipts.json"
OURS, CONTROL = "e08d759f", "59bd72a3"
R1_SOLO, R1_LO, R1_HI = 0.002358, 0.001347, 0.003368
R2_SOLO = 0.00130
WD, WP = 0.75, 0.25

rows = sorted([r for r in json.load(open(CORPUS)) if r.get("cs") and r.get("score")],
              key=lambda r: r["ts"])
ours = [r for r in rows if r["id"] == OURS][0]
ctrl = [r for r in rows if r["id"] == CONTROL][0]

# ---- A. is the session effect shared between the baseline and candidate legs?
# Genuine code differences add scatter to cand_dec that is independent of
# bl_dec, so a positive regression slope of ln(cand_dec) on ln(bl_dec) is
# evidence of a shared per-session factor.
recent = rows[-150:]
med = st.median([r["cand_dec"] for r in recent])
near = [r for r in recent if abs(math.log(r["cand_dec"] / med)) < 0.05]
print(f"[shared-session test] {len(near)} recent receipts within 5% of the "
      f"frontier decode time {med:.9f}")


def ols(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    s2 = sum(e * e for e in resid) / (len(xs) - 2)
    se = math.sqrt(s2 / sxx)
    syy = sum((y - my) ** 2 for y in ys)
    r = sxy / math.sqrt(sxx * syy)
    return b, se, r, math.sqrt(s2)


for tag, leg in (("decode", ("bl_dec", "cand_dec")), ("prefill", ("bl_pre", "cand_pre"))):
    xs = [math.log(r[leg[0]]) for r in near]
    ys = [math.log(r[leg[1]]) for r in near]
    b, se, r, sd_res = ols(xs, ys)
    print(f"  {tag:8s} slope {b:+.3f} +- {se:.3f}  (t={b/se:+.2f})  r={r:+.3f}  "
          f"sd(ln bl)={100*st.stdev(xs):.3f}%  sd(ln cand)={100*st.stdev(ys):.3f}%")
    print(f"           -> session factor is "
          f"{'SHARED (paired score is the tighter statistic)' if b / se > 2 else 'NOT shared (pinned cs is the tighter statistic)'}")

# empirical check: scatter of cs vs score on the near-frontier subset
for tag, key in (("pinned cs", "cs"), ("paired score", "score")):
    v = [r[key] for r in near]
    print(f"  scatter of {tag:13s} on that subset: {100*st.stdev(v)/st.mean(v):.4f} %")

# ---- B. decode-restricted additivity ---------------------------------------
# sigma of the decode leg, expressed in cs-percent units (weight .75)
sd_dec_leg = 100.0 * WD * st.stdev([math.log(r["bl_dec"]) for r in rows[-100:]])
sd_pre_leg = 100.0 * WP * st.stdev([math.log(r["bl_pre"]) for r in rows[-100:]])
print(f"\n[noise budget of cs, last 100 receipts, cs-percent units]")
print(f"  decode  leg sigma {sd_dec_leg:.4f} %")
print(f"  prefill leg sigma {sd_pre_leg:.4f} %")
print(f"  quadrature total  {math.hypot(sd_dec_leg, sd_pre_leg):.4f} %")
print(f"  prefill share of the variance: "
      f"{100*sd_pre_leg**2/(sd_dec_leg**2+sd_pre_leg**2):.1f} %")

meas_dec = 100.0 * WD * math.log(ctrl["cand_dec"] / ours["cand_dec"])
meas_pre = 100.0 * WP * math.log(ctrl["cand_pre"] / ours["cand_pre"])
pred = 100.0 * (R1_SOLO + R2_SOLO)
sig_r1 = 100.0 * (R1_HI - R1_LO) / (2 * 1.96)
sig_pred = math.hypot(sig_r1, sig_r1)

for tag, meas, sd_leg in (("cs (decode+prefill)", meas_dec + meas_pre,
                           math.hypot(sd_dec_leg, sd_pre_leg)),
                          ("decode leg only", meas_dec, sd_dec_leg)):
    sig_meas = sd_leg * math.sqrt(2.0)
    I = meas - pred
    sig_I = math.hypot(sig_meas, sig_pred)
    hw = 1.96 * sig_I
    print(f"\n[additivity | {tag}]")
    print(f"  measured           {meas:+.4f} % +- {sig_meas:.4f}")
    print(f"  additive predicted {pred:+.4f} % +- {sig_pred:.4f}")
    print(f"  interaction I      {I:+.4f} % +- {sig_I:.4f}   "
          f"95% [{I-hw:+.4f}, {I+hw:+.4f}]")
    print(f"  excludes I=0?              {'YES' if abs(I) > hw else 'NO'}")
    print(f"  excludes full cancellation (I={-pred:+.4f})? "
          f"{'YES' if abs(I + pred) > hw else 'NO'}")
    print(f"  -> the receipt resolves I only to +-{hw:.3f} %, while the effect "
          f"being tested is {pred:.3f} %")
    print(f"  -> power ratio (resolution / effect): {hw/pred:.1f}x too coarse"
          if hw > pred else "  -> adequately powered")

# ---- C. how many receipts would a decisive test have needed? ---------------
print("\n[design] receipts needed to resolve the additive effect at 95%/80% power")
for tag, sd_leg in (("cs", math.hypot(sd_dec_leg, sd_pre_leg)),
                    ("decode leg only", sd_dec_leg)):
    # paired arms, n receipts each; delta se = sd*sqrt(2/n); need 2.8*se < pred
    n = 2.0 * (2.8 * sd_leg / pred) ** 2
    print(f"  using {tag:16s} sigma {sd_leg:.4f} % -> n ~ {math.ceil(n):3d} "
          f"receipts per arm ({2*math.ceil(n)} total)")
