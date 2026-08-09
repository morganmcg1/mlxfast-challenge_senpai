#!/usr/bin/env python3
"""R93-B known-magnitude ladder recovery (research only).

Fits step time against the number of injected bit-exact dispatches K and
reports the slope in microseconds per dispatch with a CI, so the same ladder
run on M5 gives a directly measured M4 -> M5 transfer factor as a ratio of
slopes.

The estimator is a WITHIN-RUN block contrast. Every `mirror:` block contains
each rung exactly twice at mirrored positions, so a linear within-run drift
cancels inside the block and the block is an independent replicate. Blocks are
the unit of analysis; CIs come from a bootstrap over blocks nested in runs
nested in processes, matching how the data were generated.

  python3 research/fern_r93_ladder.py /tmp/r93/stage3/p*.json --block 8
"""
import argparse
import json
import math
import random
import statistics
import sys


def load_blocks(paths, block_len, drop_steps, drop_warmup_runs, glue_us_per_unit=40):
    """Return {(process, run): [ {k: mean_us} per complete block ]}."""
    cells = {}
    hashes = set()
    mism = 0
    for path in sorted(paths):
        with open(path) as fh:
            doc = json.load(fh)
        hashes.update(doc["token_stream_hashes"])
        mism += doc.get("teacher_forced_mismatches", 0)
        by_run = {}
        for rec in doc["records"]:
            if drop_warmup_runs and rec.get("warmup_run"):
                continue
            by_run.setdefault((rec["process"], rec["run"]), []).append(rec)
        for key, recs in by_run.items():
            recs.sort(key=lambda r: r["step"])
            recs = [r for r in recs if r["step"] >= drop_steps]
            # keep block alignment: start at the next block boundary
            start = 0
            while recs and (recs[start]["step"] % block_len) != 0:
                start += 1
                if start >= len(recs):
                    break
            recs = recs[start:]
            blocks = []
            for i in range(0, len(recs) - block_len + 1, block_len):
                chunk = recs[i:i + block_len]
                agg = {}
                for r in chunk:
                    agg.setdefault(r["k"], []).append(r["us"])
                blocks.append({k: statistics.fmean(v) for k, v in agg.items()})
            if blocks:
                cells[key] = blocks
    return cells, hashes, mism


def ols(points):
    """Slope/intercept of us on K, plus R^2."""
    n = len(points)
    xbar = statistics.fmean(x for x, _ in points)
    ybar = statistics.fmean(y for _, y in points)
    sxx = sum((x - xbar) ** 2 for x, _ in points)
    sxy = sum((x - xbar) * (y - ybar) for x, y in points)
    b = sxy / sxx
    a = ybar - b * xbar
    ss_tot = sum((y - ybar) ** 2 for _, y in points)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in points)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return b, a, r2


def block_slope(block):
    """Per-block OLS slope over the rungs present in that block."""
    pts = sorted(block.items())
    if len(pts) < 2:
        return None
    b, _, _ = ols(pts)
    return b


def pct(xs, q):
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--block", type=int, default=8,
                    help="steps per mirrored ladder block")
    ap.add_argument("--drop-steps", type=int, default=16)
    ap.add_argument("--keep-warmup-runs", dest="drop_warmup_runs",
                    action="store_false", default=True)
    ap.add_argument("--bootstrap", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=93)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    cells, hashes, mism = load_blocks(
        args.files, args.block, args.drop_steps, args.drop_warmup_runs)
    if not cells:
        raise SystemExit("no complete blocks found")
    print(f"token_stream_hashes={sorted(hashes)} teacher_forced_mismatches={mism}")
    if len(hashes) != 1:
        print("WARNING: token stream is not identical across all processes")

    all_blocks = [b for blocks in cells.values() for b in blocks]
    rungs = sorted({k for b in all_blocks for k in b})
    n_blocks = len(all_blocks)
    print(f"\nblocks={n_blocks} across {len(cells)} (process,run) cells; "
          f"rungs K={rungs}")

    # Per-rung block-paired deltas against K=0.
    base = rungs[0]
    print(f"\nper-rung paired delta vs K={base} (block-paired, us/step):")
    rng = random.Random(args.seed)
    cell_keys = sorted(cells)
    deltas_out = {}

    def resample_blocks():
        boot = []
        for _ in range(len(cell_keys)):
            key = cell_keys[rng.randrange(len(cell_keys))]
            blocks = cells[key]
            for _ in range(len(blocks)):
                boot.append(blocks[rng.randrange(len(blocks))])
        return boot

    boot_sets = [resample_blocks() for _ in range(args.bootstrap)]

    for k in rungs[1:]:
        d = [b[k] - b[base] for b in all_blocks if k in b and base in b]
        if not d:
            continue
        point = statistics.fmean(d)
        bs = []
        for boot in boot_sets:
            dd = [b[k] - b[base] for b in boot if k in b and base in b]
            if dd:
                bs.append(statistics.fmean(dd))
        lo, hi = pct(bs, 0.025), pct(bs, 0.975)
        per_disp = point / (k - base) if k != base else float("nan")
        resolved = "RESOLVED" if lo > 0 or hi < 0 else "not resolved"
        print(f"  K={k:4d}: delta={point:+9.2f}  95% CI [{lo:+8.2f}, {hi:+8.2f}]"
              f"  ({per_disp:+.3f} us/dispatch)  n={len(d)}  {resolved}")
        deltas_out[k] = {"delta_us": point, "ci": [lo, hi],
                         "us_per_dispatch": per_disp, "n_blocks": len(d),
                         "resolved": lo > 0 or hi < 0}

    # Pooled slope: OLS on the block-mean profile, bootstrapped over blocks.
    profile = {}
    for k in rungs:
        vals = [b[k] for b in all_blocks if k in b]
        profile[k] = statistics.fmean(vals)
    slope, intercept, r2 = ols(sorted(profile.items()))
    bs = []
    for boot in boot_sets:
        prof = {}
        for k in rungs:
            vals = [b[k] for b in boot if k in b]
            if vals:
                prof[k] = statistics.fmean(vals)
        if len(prof) >= 2:
            bs.append(ols(sorted(prof.items()))[0])
    slo, shi = pct(bs, 0.025), pct(bs, 0.975)
    print(f"\npooled ladder slope: {slope*1e3:.4f} ns/dispatch "
          f"= {slope:.5f} us/dispatch  95% CI [{slo:.5f}, {shi:.5f}]  R^2={r2:.5f}")
    print(f"  intercept (K=0 step time) = {intercept:.1f} us")
    print("  rung profile:")
    for k in rungs:
        pred = intercept + slope * k
        print(f"    K={k:4d}  mean={profile[k]:9.2f} us  fit={pred:9.2f}  "
              f"resid={profile[k]-pred:+7.2f}")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump({
                "rungs": rungs, "n_blocks": n_blocks, "block_len": args.block,
                "slope_us_per_dispatch": slope, "slope_ci": [slo, shi],
                "intercept_us": intercept, "r2": r2,
                "profile": {str(k): profile[k] for k in rungs},
                "deltas": {str(k): v for k, v in deltas_out.items()},
                "token_stream_hashes": sorted(hashes),
                "teacher_forced_mismatches": mism,
            }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
