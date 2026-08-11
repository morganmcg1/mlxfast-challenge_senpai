#!/usr/bin/env python3
"""Classify every recent receipt as pre- or post- alphonse's merged gate_sp.

CORRECTION: an earlier version of this script passed receipt-ID prefixes where
commit SHAs were required, so every lookup missed and reported 'object absent'.
These are the commit SHAs as recorded by the benchmark itself in
officialMetrics.commit.

A receipt contains the fused-gate win iff the merge head 9e97cc7d is an ancestor
of its commit.
"""
import statistics
import subprocess

GATE_MERGE = "9e97cc7dd0e8bae3a859e98a43f02be061ed3c01"

# receipt id, createdAt, commit, decode leg, label
receipts = [
    ("db4fa283", "04:44:34Z", "4a6c2df1c96fd568e13a4a3f13f8292cb31a05df", 0.0049317789765625, "advisor r119b"),
    ("47fa4d85", "04:20:06Z", "62ab8d7555ff6dc1815c65057b80f9824cdaefc1", 0.00491371875, "advisor r119a"),
    ("53c8acac", "03:55:01Z", "5949b5c6c10c334ee6ca01738c260dd4e4e1b75d", 0.0049052083359375, "r118a"),
    ("354c40c7", "03:30:50Z", "8996ba2a2fede0106e4553ecbfc454de994e5f4c", 0.0049124921875, "r117b"),
    ("cdf740c2", "03:05:59Z", "fedeca195678ce7c0d89d6af6a8ec3698bec171a", 0.0049487503203125, "r117-01"),
    ("be958bcd", "02:23:20Z", "07f0ec06dad78822f7f2c8b449602960aa57a069", 0.004930751296875, "A2"),
    ("cb4de9e0", "01:54:46Z", "fe610f60ecaa41dd93b0e6cf2994eba6ba1586f3", 0.004897051109375, "ticket6"),
    ("0531544b", "01:31:01Z", "0a81e48b91c2617fdba30243ddf0f99e3a1fae0a", 0.00490711328125, "ticket5"),
    ("ed40f3ee", "01:07:24Z", "d567a72a3b02d936ed37d909ece0b2cb1dca3163", 0.0049282265625, "ticket4"),
    ("2aedeb87", "00:39:49Z", "25d1f816affdd5baf7c0959554be8d4345cebab7", 0.0049312080078125, "r113"),
]


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


print(f"{'receipt':10} {'createdAt':11} {'commit':10} {'arm':14} {'local':6} {'has gate'}")
pre, post, unknown = [], [], []
for rid, created, sha, decode, label in receipts:
    ex = run(["git", "cat-file", "-e", sha + "^{commit}"])
    if ex.returncode != 0:
        print(f"{rid:10} {created:11} {sha[:10]:10} {label:14} {'no':6} UNKNOWN")
        unknown.append((rid, decode, label))
        continue
    anc = run(["git", "merge-base", "--is-ancestor", GATE_MERGE, sha])
    has = anc.returncode == 0
    print(f"{rid:10} {created:11} {sha[:10]:10} {label:14} {'yes':6} {'YES' if has else 'no'}")
    (post if has else pre).append((rid, decode, label))

print()
print(f"post-gate n={len(post)}: {[r[0] for r in post]}")
print(f"pre-gate  n={len(pre)}: {[r[0] for r in pre]}")
print(f"unknown   n={len(unknown)}: {[r[0] for r in unknown]}")

if len(post) >= 2 and len(pre) >= 2:
    mp = statistics.fmean([r[1] for r in post])
    mq = statistics.fmean([r[1] for r in pre])
    sp = statistics.stdev([r[1] for r in post])
    sq = statistics.stdev([r[1] for r in pre])
    print()
    print(f"post-gate decode mean {mp:.10f} sd {sp:.10f} n={len(post)}")
    print(f"pre-gate  decode mean {mq:.10f} sd {sq:.10f} n={len(pre)}")
    print(f"delta = {(mp / mq - 1.0) * 100:+.4f}%  (negative = post-gate faster)")
    print("predicted from the merged claim: -0.591%")
