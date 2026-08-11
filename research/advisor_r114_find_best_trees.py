#!/usr/bin/env python3
"""R114d -- locate the fastest TREES on the board, ours and the field's.

R114c established that leg metrics are ~20-170x cleaner than the score, and
that our HEAD tree is at parity with the crown receipt.  It also turned up two
facts that need names and dates attached before anything is decided:

  * our own solver account (morganmcg1, shared with the cedar launch) has a
    receipt whose candidate decode is 0.62% of score better than our HEAD;
  * the crown receipt cc6ddc1 is NOT its own solver's fastest tree -- their best
    is another 0.89% faster on decode and simply never drew a lucky baseline.

`mlxfast reset <submission>` restores editable paths from ANY submission's
commit, accepted or not.  So a faster tree inside our own account is not
trivia; it is a retrievable artifact.  This script finds and dates them.

Careful with the score column: because the baseline arm carries 96% of score
variance, ranking receipts by score finds lucky baselines, not fast code.
Everything here ranks by the CANDIDATE legs, expressed as the score the tree
would earn on a fixed reference baseline.
"""

from __future__ import annotations

import json
import os
import statistics as st
import urllib.parse
import urllib.request
from collections import defaultdict

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
CACHE = "/tmp/mlxfast_subs_r114.json"
OURS = ["c1c0ba2", "2771067", "8858427", "2aedeb8"]
WD, WP = 0.75, 0.25

# Fixed reference baseline = the mean baseline arm over the whole feed.
# Its absolute value is arbitrary; only ratios between trees matter.


def fetch(path=CACHE):
    if path and os.path.exists(path):
        return json.load(open(path))
    token = os.environ["MLXFAST_API_TOKEN"]
    ref = urllib.parse.quote(BENCH, safe="")
    url = "%s/api/benchmarks/%s/submissions" % (API, ref)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    json.dump(data, open(path, "w"))
    return data


def load():
    out = []
    for s in fetch()["submissions"]:
        m = s.get("officialMetrics")
        if not m:
            continue
        if isinstance(m, str):
            m = json.loads(m)
        if not (m.get("baseline_decode_seconds_per_token") and m.get("prefill_seconds_per_token")
                and m.get("baseline_prefill_seconds_per_token") and m.get("decode_seconds_per_token")):
            continue
        out.append({
            "id": s.get("id", ""), "at": s.get("createdAt", ""),
            "who": s.get("solverUsername", ""), "score": s.get("officialScore"),
            "status": s.get("status", ""),
            "ok": bool(m.get("passed_correctness")),
            "cd": m["decode_seconds_per_token"], "bd": m["baseline_decode_seconds_per_token"],
            "cp": m["prefill_seconds_per_token"], "bp": m["baseline_prefill_seconds_per_token"],
        })
    out.sort(key=lambda r: r["at"])
    return out


def main():
    rows = load()
    ok = [r for r in rows if r["ok"]]
    RBD = st.mean([r["bd"] for r in ok])
    RBP = st.mean([r["bp"] for r in ok])

    def tscore(r):
        """Score this TREE would earn on the fixed reference baseline."""
        return (RBD / r["cd"]) ** WD * (RBP / r["cp"]) ** WP

    ours = [r for r in rows if any(r["id"].startswith(p) for p in OURS)]
    ohead = st.mean([tscore(r) for r in ours])

    print("=" * 104)
    print("Reference baseline (feed mean): decode %.6f ms  prefill %.4f us   n=%d"
          % (RBD * 1e3, RBP * 1e6, len(ok)))
    print("Our HEAD tree's de-luckied score: %.8f" % ohead)
    print("Crown published score           : 2.61650354381456  (receipt cc6ddc1)")
    print("=" * 104)
    print()

    print("-" * 104)
    print("(A) TOP 25 TREES ON THE WHOLE BOARD, ranked by de-luckied tree score")
    print("-" * 104)
    print("  %-9s %-13s %-18s %-11s %-13s %-11s %-9s" %
          ("id", "solver", "created", "tree score", "vs our HEAD", "status", "published"))
    for r in sorted(ok, key=tscore, reverse=True)[:25]:
        t = tscore(r)
        mark = "  <== OURS" if any(r["id"].startswith(p) for p in OURS) else ""
        print("  %-9s %-13s %-18s %-11.6f %+-13.4f %-11s %-9.5f%s"
              % (r["id"][:7], r["who"][:13], r["at"][:16], t,
                 100 * (t / ohead - 1), r["status"][:11],
                 r["score"] or 0.0, mark))
    print()

    print("-" * 104)
    print("(B) OUR OWN ACCOUNT (morganmcg1 = maple + cedar): top 15 trees")
    print("-" * 104)
    mine = [r for r in ok if r["who"] == "morganmcg1"]
    print("  %d correctness-passing receipts on this account" % len(mine))
    print("  %-9s %-18s %-12s %-13s %-11s %-11s" %
          ("id", "created", "tree score", "vs our HEAD", "status", "published"))
    for r in sorted(mine, key=tscore, reverse=True)[:15]:
        t = tscore(r)
        mark = "  <== HEAD-class" if any(r["id"].startswith(p) for p in OURS) else ""
        print("  %-9s %-18s %-12.6f %+-13.4f %-11s %-11.5f%s"
              % (r["id"][:7], r["at"][:16], t, 100 * (t / ohead - 1),
                 r["status"][:11], r["score"] or 0.0, mark))
    print()
    print("  NOTE: `mlxfast reset <submission>` restores editable paths from any of")
    print("  these, accepted or not. A tree above our HEAD here is retrievable.")
    print()

    print("-" * 104)
    print("(C) IS THE CROWN'S SOLVER SITTING ON A BETTER TREE?")
    print("-" * 104)
    ag = [r for r in ok if r["who"] == "a-github-name"]
    print("  a-github-name, top 8 trees by de-luckied score (n=%d receipts):" % len(ag))
    for r in sorted(ag, key=tscore, reverse=True)[:8]:
        t = tscore(r)
        print("    %-9s %-18s tree %.6f  (%+.4f%% vs our HEAD)  published %.5f"
              % (r["id"][:7], r["at"][:16], t, 100 * (t / ohead - 1), r["score"] or 0))
    print()

    print("-" * 104)
    print("(D) THE THREAT MODEL: if each solver's BEST tree drew a mean baseline")
    print("-" * 104)
    best = {}
    for r in ok:
        t = tscore(r)
        if r["who"] not in best or t > best[r["who"]][0]:
            best[r["who"]] = (t, r)
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
    print("  %-20s %-12s %-13s %-18s" % ("solver", "best tree", "vs our HEAD", "last seen"))
    for who, (t, r) in ranked[:12]:
        last = max(x["at"] for x in ok if x["who"] == who)
        print("  %-20s %-12.6f %+-13.4f %-18s" % (who[:20], t, 100 * (t / ohead - 1), last[:16]))
    ahead = [1 for _, (t, _) in ranked if t > ohead]
    print()
    print("  solvers with a tree ahead of ours: %d of %d" % (len(ahead), len(ranked)))


if __name__ == "__main__":
    main()
