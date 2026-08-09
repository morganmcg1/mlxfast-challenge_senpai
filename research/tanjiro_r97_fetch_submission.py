#!/usr/bin/env python3
"""Dump full official metrics for mlxfast submissions.

`mlxfast submissions` truncates the metrics column, hiding the per-axis
baseline/candidate seconds-per-token needed to score a receipt against a
preregistered read-out table, and to estimate session-to-session noise.

    tanjiro_r97_fetch_submission.py <submission-id>   # one receipt, full JSON
    tanjiro_r97_fetch_submission.py --table [N]       # last N receipts, per-axis
"""
import json
import os
import sys
import urllib.request

CFG = json.load(open(os.path.expanduser("~/.config/mlxfast/config.json")))
BASE = CFG["apiBaseUrl"].rstrip("/")
BENCHMARK = "1854efdf-feba-4773-bae9-b80520881a74"


def get(path):
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {CFG['token']}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def metrics_of(sub):
    m = sub.get("officialMetrics")
    return json.loads(m) if isinstance(m, str) else m


if sys.argv[1] == "--table":
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    subs = get(f"/api/benchmarks/{BENCHMARK}/submissions")
    subs = subs["submissions"] if isinstance(subs, dict) else subs
    mine = [s for s in subs if s.get("solverAccountId") == CFG["accountId"]]
    mine.sort(key=lambda s: s["createdAt"])
    hdr = ("created", "sub", "commit", "status", "score",
           "bl_pre_ms", "cd_pre_ms", "pre_su", "bl_dec_ms", "cd_dec_ms", "dec_su", "corr")
    print(("{:<17} {:<9} {:<8} {:<9} {:>10} " + "{:>10} " * 6 + "{:>5}").format(*hdr))
    for s in mine[-limit:]:
        m = metrics_of(s) or {}
        if not m:
            print("{:<17} {:<9} {:<8} {:<9} {:>10}".format(
                s["createdAt"][:16], s["id"][:8],
                (s.get("submissionCommitSha") or "-")[:7], s["status"], "n/a"))
            continue
        print("{:<17} {:<9} {:<8} {:<9} {:>10.5f} {:>10.3f} {:>10.3f} {:>10.5f} "
              "{:>10.4f} {:>10.4f} {:>10.5f} {:>5}".format(
                  s["createdAt"][:16], s["id"][:8],
                  (s.get("submissionCommitSha") or "-")[:7], s["status"],
                  s.get("officialScore") or float("nan"),
                  512000 * m["baseline_prefill_seconds_per_token"],
                  512000 * m["prefill_seconds_per_token"],
                  m["prefill_speedup"],
                  1000 * m["baseline_decode_seconds_per_token"],
                  1000 * m["decode_seconds_per_token"],
                  m["decode_speedup"],
                  "ok" if m.get("passed_correctness") else "FAIL"))
    sys.exit(0)

sub = get(f"/api/submissions/{sys.argv[1]}")
sub = sub.get("submission", sub)
for field in ("status", "officialScore", "improved", "rejectionReason",
              "promotionStatus", "promotionReason", "createdAt", "submissionCommitSha"):
    print(f"{field} = {sub.get(field)}")
print(json.dumps(metrics_of(sub), indent=2, sort_keys=True))
