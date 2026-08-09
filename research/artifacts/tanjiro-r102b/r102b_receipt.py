#!/usr/bin/env python3
"""R102-B P4: decompose the composed-restoration receipt against the corpus.

The corpus has no repeated official commit (1203 receipts, 1203 distinct
commits), so within-commit replicates cannot supply the noise scale. The
pinned baseline arm *is* byte-identical code in every session, so the scatter
of a pinned-constant score recomputed from (bl_dec, bl_pre) is a direct
measurement of per-session harness noise, and cs inherits exactly that noise
because cs is computed from the candidate legs with the same pinned constants.
"""
import json
import math
import statistics as st
import sys

CORPUS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r102b-receipts.json"
OURS = "e08d759f"
CONTROL = "59bd72a3"
CONTROL_CS = 2.575633
RECORD = 2.61650354381456
R1_SOLO, R1_LO, R1_HI = 0.002358, 0.001347, 0.003368
R2_SOLO = 0.00130
WD, WP = 0.75, 0.25

rows = [r for r in json.load(open(CORPUS)) if r.get("cs") and r.get("score")]
rows.sort(key=lambda r: r["ts"])
print(f"[corpus] {len(rows)} receipts  {rows[0]['ts']} .. {rows[-1]['ts']}  "
      f"{len({r['commit'] for r in rows})} distinct commits")


def sc(dec_su, pre_su):
    return dec_su ** WD * pre_su ** WP


res = [abs(sc(r["dec_su"], r["pre_su"]) / r["score"] - 1.0) for r in rows]
print(f"\n[formula] score == dec_su^.75 * pre_su^.25   max rel resid "
      f"{max(res):.2e}  -> {'CONFIRMED' if max(res) < 1e-9 else 'REJECTED'}")

Ks = [math.log(r["cs"]) + WD * math.log(r["cand_dec"]) + WP * math.log(r["cand_pre"])
      for r in rows]
K = st.median(Ks)
print(f"[formula] cs pinned constant K = .75 lnMB_D + .25 lnMB_P = {K:.9f}  "
      f"spread {max(Ks) - min(Ks):.2e}  "
      f"-> {'CONFIRMED' if max(Ks) - min(Ks) < 1e-9 else 'REJECTED'}")


def cs_of(dec, pre):
    return math.exp(K - WD * math.log(dec) - WP * math.log(pre))


for r in rows:
    r["b_cs"] = cs_of(r["bl_dec"], r["bl_pre"])


def noise(sub, tag):
    v = [x["b_cs"] for x in sub]
    m = st.mean(v)
    sd = 100.0 * st.stdev(v) / m
    sdd = 100.0 * WD * st.stdev([math.log(x["bl_dec"]) for x in sub])
    sdp = 100.0 * WP * st.stdev([math.log(x["bl_pre"]) for x in sub])
    print(f"  {tag:26s} n={len(sub):4d}  mean b_cs {m:.6f}  sd {sd:.4f} %"
          f"   (decode leg {sdd:.4f} %, prefill leg {sdp:.4f} %)")
    return sd


print("\n[session noise] scatter of the pinned score recomputed on the "
      "byte-identical baseline arm")
sd_all = noise(rows, "full corpus")
sd_200 = noise(rows[-200:], "last 200 receipts")
sd_100 = noise(rows[-100:], "last 100 receipts")
ours = [r for r in rows if r["id"] == OURS][0]
day = [r for r in rows if r["ts"][:10] == ours["ts"][:10]]
sd_day = noise(day, f"same day {ours['ts'][:10]}")
SIG = sd_100
print(f"  -> adopting sigma_session = {SIG:.4f} % (last 100 receipts)")

print("\n[our receipt]")
for k in ("full_id", "ts", "commit", "solver", "status", "score", "cs",
          "cand_dec", "cand_pre", "bl_dec", "bl_pre", "dec_su", "pre_su"):
    print(f"  {k:9s} {ours[k]}")

ctrl = [r for r in rows if r["id"] == CONTROL]
if ctrl:
    c = ctrl[0]
    print(f"\n[control receipt {CONTROL}]  ts {c['ts']}  cs {c['cs']:.6f}  "
          f"cand_dec {c['cand_dec']}  cand_pre {c['cand_pre']}")
else:
    c = None
    print(f"\n[control receipt {CONTROL}] NOT in corpus; using recorded cs "
          f"{CONTROL_CS}")

meas = 100.0 * (ours["cs"] / CONTROL_CS - 1.0)
pred = 100.0 * (R1_SOLO + R2_SOLO)
inter = meas - pred
sig_r1 = 100.0 * (R1_HI - R1_LO) / (2 * 1.96)
sig_r2 = sig_r1
sig_meas = SIG * math.sqrt(2.0)
sig_pred = math.hypot(sig_r1, sig_r2)
sig_I = math.hypot(sig_meas, sig_pred)
print("\n[additivity]  (all figures in % of cs)")
print(f"  control cs                 {CONTROL_CS:.6f}")
print(f"  measured cs                {ours['cs']:.6f}")
print(f"  measured delta             {meas:+.4f} % +- {sig_meas:.4f} (2 single draws)")
print(f"  additive prediction        {pred:+.4f} % +- {sig_pred:.4f} "
      f"(R1 {100*R1_SOLO:+.4f}+-{sig_r1:.4f}, R2 {100*R2_SOLO:+.4f}+-{sig_r2:.4f})")
print(f"  implied interaction I      {inter:+.4f} % +- {sig_I:.4f}")
print(f"  I / sigma_I                {inter/sig_I:+.2f}")
print(f"  95% band on I              [{inter-1.96*sig_I:+.4f}, {inter+1.96*sig_I:+.4f}] %")
print(f"  I distinguishable from 0?        "
      f"{'YES' if abs(inter) > 1.96*sig_I else 'NO'}")
print(f"  I distinguishable from -(R1+R2)? "
      f"{'YES' if abs(inter + pred) > 1.96*sig_I else 'NO'} "
      f"(full cancellation needs I = {-pred:+.4f} %)")
print(f"  measured delta > 0 at 95%?       "
      f"{'YES' if meas > 1.96*sig_meas else 'NO'}")

if c:
    dd = 100.0 * WD * math.log(c["cand_dec"] / ours["cand_dec"])
    dp = 100.0 * WP * math.log(c["cand_pre"] / ours["cand_pre"])
    print("\n[log-split of the measured delta vs the control receipt]")
    print(f"  decode  leg  {dd:+.4f} %   {c['cand_dec']:.12f} -> {ours['cand_dec']:.12f}")
    print(f"  prefill leg  {dp:+.4f} %   {c['cand_pre']:.12f} -> {ours['cand_pre']:.12f}")
    print(f"  sum          {dd+dp:+.4f} %  (vs measured {meas:+.4f} %)")
    print("  NOTE: R1 and R2 touch decode attention only, so the prefill leg "
          "is an independent noise draw expected to be consistent with 0.")

need = 100.0 * (RECORD / ours["cs"] - 1.0)
z = need / (SIG * math.sqrt(2.0))
p = 0.5 * math.erfc(z / math.sqrt(2.0))
print("\n[record]")
print(f"  record cs                  {RECORD:.6f}")
print(f"  our cs                     {ours['cs']:.6f}")
print(f"  gap to record              {need:+.4f} %")
print(f"  z per fresh draw           {z:.2f}   per-draw P(beat record) ~ {p:.3e}")

print("\n[corpus top 8 by cs]")
for r in sorted(rows, key=lambda x: -x["cs"])[:8]:
    print(f"  {r['cs']:.6f}  {r['id']}  {r['ts']}  {r['solver']:<16s} {r['status']}")
mine = sorted([r for r in rows if r["solver"] == ours["solver"]], key=lambda x: -x["cs"])
rank = [r["id"] for r in mine].index(OURS) + 1
print(f"\n[solver {ours['solver']}] {len(mine)} receipts; ours ranks "
      f"{rank}/{len(mine)} by cs; best {mine[0]['cs']:.6f} ({mine[0]['id']})")
allrank = [r["id"] for r in sorted(rows, key=lambda x: -x["cs"])].index(OURS) + 1
print(f"[corpus] ours ranks {allrank}/{len(rows)} by cs overall")
print("\n[same-day receipts]")
for r in sorted(day, key=lambda x: x["ts"]):
    print(f"  {r['ts']}  {r['id']}  cs {r['cs']:.6f}  {r['solver']:<16s} {r['status']}")
