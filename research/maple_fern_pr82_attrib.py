#!/usr/bin/env python3
"""Merge for the PR82 K / KI attribution sequence.

Executed sequence (positions are launch order on one host, one run each):

    1  K   base tree            (detached ede561b6)
    2  KI  attribution tree     (maple-fern/pr82-attrib-ki-local)
    3  KI  attribution tree
    4  I   candidate tree       <-- MIS-ARMED, discarded, see note below
    5  K   base tree            (detached ede561b6)

Position 4 was intended to be K but a `git checkout` back to the submission
branch raced the non-blocking benchmark build, so that run compiled and
measured the candidate tree.  It is detected here by harness_hash and excluded
from the K/KI contrast; it is reported separately as an unpaired observation.

Each arm carries a distinct harness_hash, so the arm label is *verified*
against the artifact rather than trusted from the launch order.
"""
import json
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pr82-scores")

BASE_H = "56ba8b02"
KI_H = "0dd99ac5"
CAND_H = "712c4035"

EXPECT = {"K": BASE_H, "KI": KI_H, "I": CAND_H}

ORDER = [("K", 1, "score.attrib.K1.json"),
         ("KI", 2, "score.attrib.KI1.json"),
         ("KI", 3, "score.attrib.KI2.json"),
         ("I", 4, "score.attrib.pos4-CANDIDATE-mislabelled.json"),
         ("K", 5, "score.attrib.K2.json")]


def find(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                return v
            r = find(v, key)
            if r is not None:
                return r
    return None


rows = []
for arm, pos, path in ORDER:
    d = json.load(open(os.path.join(HERE, path)))
    rows.append(dict(arm=arm, pos=pos,
                     decode=find(d, "decode_seconds_per_token"),
                     prefill=find(d, "prefill_seconds_per_token"),
                     corr=find(d, "passed_correctness"),
                     mad=find(d, "max_abs_diff"),
                     golden=find(d, "golden_hash"),
                     harness=find(d, "harness_hash")))

for r in rows:
    tag = "" if r["harness"].startswith(EXPECT[r["arm"]]) else "  <-- ARM/HASH MISMATCH"
    print(f"pos {r['pos']} arm {r['arm']:3s} decode {r['decode']:.12f} "
          f"prefill {r['prefill']:.12f} corr {r['corr']} mad {r['mad']} "
          f"golden {r['golden'][:8]} harness {r['harness'][:8]}{tag}")

for r in rows:
    assert r["harness"].startswith(EXPECT[r["arm"]]), f"pos {r['pos']} arm mislabelled"

K = [r for r in rows if r["arm"] == "K"]
KI = [r for r in rows if r["arm"] == "KI"]
I = [r for r in rows if r["arm"] == "I"]

mkd = sum(r["decode"] for r in K) / len(K)
mkid = sum(r["decode"] for r in KI) / len(KI)
mkp = sum(r["prefill"] for r in K) / len(K)
mkip = sum(r["prefill"] for r in KI) / len(KI)

print()
print(f"K  mean position = {sum(r['pos'] for r in K) / len(K):.2f}   "
      f"KI mean position = {sum(r['pos'] for r in KI) / len(KI):.2f}")
print(f"mean K  decode = {mkd:.12f}   mean KI decode = {mkid:.12f}")
print(f"mean K  prefill= {mkp:.12f}   mean KI prefill= {mkip:.12f}")
dg = mkd / mkid
pg = mkp / mkip
print(f"decode_gain(KI vs K)  = {dg:.9f}   ({(dg - 1) * 100:+.3f} %)")
print(f"prefill_gain(KI vs K) = {pg:.9f}   ({(pg - 1) * 100:+.3f} %)")
print(f"paired_estimate       = {dg ** 0.75 * pg ** 0.25:.9f}")
print()
print(f"adjacent K1/KI1 decode_gain = {K[0]['decode'] / KI[0]['decode']:.9f}")
print(f"adjacent K2/KI2 decode_gain = {K[1]['decode'] / KI[1]['decode']:.9f}")
print(f"K  repeat spread K2/K1-1   = {(K[1]['decode'] / K[0]['decode'] - 1) * 100:+.3f} %")
print(f"KI repeat spread KI2/KI1-1 = {(KI[1]['decode'] / KI[0]['decode'] - 1) * 100:+.3f} %")
print()
print(f"unpaired candidate observation at pos 4: decode {I[0]['decode']:.12f} "
      f"(K mean {mkd:.12f}, ratio K/I = {mkd / I[0]['decode']:.9f})")
print()
print("distinct golden_hash :", len({r["golden"] for r in rows}))
print("distinct harness_hash:", sorted({r["harness"][:8] for r in rows}))
print("all correctness pass :", all(r["corr"] for r in rows))
print("all max_abs_diff 0   :", all(r["mad"] == 0 for r in rows))
