#!/usr/bin/env python3
"""READ-ONLY: find true draw repeats by git TREE hash, not commit sha.

Context.  research/fern_r109f_same_commit_draws.py established two facts:
  * officialScore == decode_speedup**0.75 * prefill_speedup**0.25 exactly
    (max rel err 4.7e-15 over 1290 rows), so no "draw" multiplier hides in the
    scoring formula -- all luck is measurement noise in the two speedups;
  * no commit sha was ever scored twice, so same-commit repeats do not exist.

But a rebase or an empty-message amend produces a *different commit sha with an
identical tree*.  Those are genuine repeat draws of literally identical code, and
they are the only unbiased sample of channel luck available.  This script maps
each of our scored submissions to its git tree hash (when the commit is present
in the local clone) and reports the score spread within each tree group.

Usage: python3 research/fern_r109f_tree_repeats.py <queue.json> [...]
"""
import collections
import json
import math
import statistics
import subprocess
import sys

OURS = "morganmcg1"
BAR = 2.61955310948


def load(paths):
    seen, rows = set(), []
    for p in paths:
        doc = json.load(open(p))
        for r in doc.get("submissions", doc):
            if r.get("id") not in seen:
                seen.add(r.get("id"))
                rows.append(r)
    return rows


def tree_of(shas):
    """Batch-resolve commit sha -> tree sha for shas present locally."""
    if not shas:
        return {}
    q = "".join(f"{s}^{{tree}}\n" for s in shas)
    p = subprocess.run(["git", "cat-file", "--batch-check"], input=q,
                       capture_output=True, text=True)
    out = {}
    for sha, line in zip(shas, p.stdout.strip().splitlines()):
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "tree":
            out[sha] = parts[0]
    return out


def main(argv):
    rows = load(argv or ["research/fern-r109f-queue-1310Z.json"])
    mine = [r for r in rows
            if r.get("solverUsername") == OURS and r.get("officialScore")
            and r.get("submissionCommitSha")]
    shas = [r["submissionCommitSha"] for r in mine]
    trees = tree_of(shas)
    print(f"our scored rows={len(mine)}  commits resolvable locally={len(trees)}")

    groups = collections.defaultdict(list)
    for r in mine:
        t = trees.get(r["submissionCommitSha"])
        if t:
            groups[t].append((r["createdAt"], float(r["officialScore"]),
                              r["submissionCommitSha"][:8]))
    rep = {t: sorted(v) for t, v in groups.items() if len(v) >= 2}
    print(f"tree groups={len(groups)}  with >=2 draws={len(rep)}"
          f"  rows in repeats={sum(len(v) for v in rep.values())}")

    pooled = []
    for t, v in sorted(rep.items(), key=lambda kv: -len(kv[1])):
        ss = [s for _, s, _ in v]
        med = statistics.median(ss)
        pooled += [s / med for s in ss]
        print(f"\n  tree {t[:8]}  n={len(ss)}  median={med:.6f}"
              f"  min={min(ss):.6f}  max={max(ss):.6f}"
              f"  spread={max(ss)/min(ss)-1:.3%}"
              f"  rel sd={statistics.pstdev(ss)/med:.3%}")
        for c, s, sha in v:
            print(f"      {c[:19]}  {sha}  {s:.6f}")

    if len(pooled) >= 3:
        pooled.sort()
        sd = statistics.pstdev(pooled)
        best = max(float(r["officialScore"]) for r in mine)
        bestmed = None
        for t, v in rep.items():
            if max(s for _, s, _ in v) == best:
                bestmed = statistics.median([s for _, s, _ in v])
        print(f"\npooled within-TREE ratio: n={len(pooled)}  sd={sd:.4%}"
              f"  min={pooled[0]:.5f}  max={pooled[-1]:.5f}")
        ref = bestmed or best
        need = BAR / ref
        z = (need - 1) / sd if sd else float("inf")
        print(f"reference tree score {ref:.6f} -> need ratio {need:.6f}"
              f" ({(need-1)*100:+.3f} %, z={z:.2f})")
        print(f"normal-tail P(one draw clears bar) = "
              f"{0.5*math.erfc(z/math.sqrt(2)):.3%}")
        k = sum(1 for x in pooled if x >= need)
        print(f"empirical exceedances in the repeat sample: {k}/{len(pooled)}")
    else:
        print("\nNot enough true repeats to estimate draw noise from tree hashes.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
