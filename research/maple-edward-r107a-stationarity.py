#!/usr/bin/env python3
"""Block-stationarity and dispersion diagnostic for one abba arm contrast.

Usage: maple-edward-r107a-stationarity.py OUTDIR REF_ARM TEST_ARM [NBLOCKS]

For every rep that contains both arms, the test arm's per-step series is
differenced against the mean of that rep's reference-arm slots at the same step
index, which cancels rep-level drift. The differences are then split into
NBLOCKS equal blocks of step indices. A pure level shift gives equal block
means; a drifting or bimodal effect does not. Per-step dispersion is reported
separately because a tail/load-imbalance mechanism inflates it while a
residency-quantization mechanism leaves it alone.
"""
import statistics
import sys
from pathlib import Path

SKIP_STEPS = 1  # step 0 carries first-dispatch JIT and cache-fill cost


def load(path):
    return [float(x) * 1000.0 for x in path.read_text().split()]


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    ref_arm, test_arm = sys.argv[2], sys.argv[3]
    nblocks = int(sys.argv[4]) if len(sys.argv) > 4 else 5

    rows = [l.split("\t") for l in (out / "index.tsv").read_text().splitlines()[1:]]
    by_rep = {}
    for rep, _pos, arm, tag in rows:
        by_rep.setdefault(rep, {}).setdefault(arm, []).append(tag)

    per_rep_blocks, ref_sd, test_sd = [], [], []
    for rep in sorted(by_rep):
        arms = by_rep[rep]
        if ref_arm not in arms or test_arm not in arms:
            continue
        ref = [load(out / f"{t}.steps") for t in arms[ref_arm]]
        test = [load(out / f"{t}.steps") for t in arms[test_arm]]
        n = min(len(s) for s in ref + test)
        base = [statistics.fmean(s[i] for s in ref) for i in range(n)]
        for s in test:
            diff = [s[i] - base[i] for i in range(SKIP_STEPS, n)]
            w = len(diff) // nblocks
            per_rep_blocks.append([statistics.fmean(diff[b * w:(b + 1) * w])
                                   for b in range(nblocks)])
        ref_sd += [statistics.stdev(s[SKIP_STEPS:n]) for s in ref]
        test_sd += [statistics.stdev(s[SKIP_STEPS:n]) for s in test]

    k = len(per_rep_blocks)
    if k < 2:
        sys.exit(f"only {k} paired series for {ref_arm}->{test_arm}")
    print(f"{out}  {ref_arm} -> {test_arm}  paired series K={k}  blocks={nblocks}")
    print("block  mean_us  95%hw   n")
    overall = []
    for b in range(nblocks):
        v = [r[b] for r in per_rep_blocks]
        overall += v
        hw = 1.96 * statistics.stdev(v) / len(v) ** 0.5
        print(f"{b:5d}  {statistics.fmean(v):+8.2f}  {hw:6.2f}  {len(v)}")
    allmeans = [statistics.fmean(r) for r in per_rep_blocks]
    hw = 1.96 * statistics.stdev(allmeans) / k ** 0.5
    print(f"  all  {statistics.fmean(allmeans):+8.2f}  {hw:6.2f}  {k}")
    spread = max(statistics.fmean([r[b] for r in per_rep_blocks])
                 for b in range(nblocks)) - \
        min(statistics.fmean([r[b] for r in per_rep_blocks]) for b in range(nblocks))
    print(f"block-mean spread {spread:.2f} us  (level shift if << |all|)")
    # per-slot sd is heavy-tailed: one stalled slot doubles the mean, so the
    # median over slots is the statistic that answers the tail-mechanism question.
    for name, agg in (("mean", statistics.fmean), ("median", statistics.median)):
        print(f"per-step sd ({name} over slots): {ref_arm} {agg(ref_sd):.2f} us, "
              f"{test_arm} {agg(test_sd):.2f} us, "
              f"ratio {agg(test_sd) / agg(ref_sd):.3f}")


if __name__ == "__main__":
    main()
