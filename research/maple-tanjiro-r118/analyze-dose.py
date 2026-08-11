#!/usr/bin/env python3
"""R118-A analysis: paired in-situ byte dose on the shared-expert gate+up QMV.

Reads one ORDER directory produced by qmv-dose-abba.sh (runN_<arm>.steps, one
decode-step wall time in ms per line) and reports, for that order ALONE:

  * per-run medians, and the per-BLOCK paired saving of every arm vs `ship`
    (block = 4 consecutive runs, one per arm, so monotone session drift and
    the first-in-block warmup penalty both cancel in the contrast);
  * a bootstrap CI on the MEDIAN paired saving (blocks resampled with
    replacement), and the mean, per the R118-A method note;
  * the negative-control arm `ctl` -- byte-identical kernel text under a
    different kernel name.  If the ctl interval EXCLUDES zero the rig is dead
    and no other number in the file may be believed;
  * a bimodality screen on the pooled raw per-step samples of each arm;
  * a raw-sample CSV for the record.

usage: analyze-dose.py <ORDER_DIR> [--warmup N] [--boot N] [--label NAME]
"""
import argparse
import csv
import glob
import math
import os
import random
import re
import statistics as st

ARMS = ["ship", "ctl", "d2", "d1"]
# device bytes each arm actually reads from the shared gate+up QMV weights,
# per call, from the source: 4 K-blocks of width 512 over 1024 output rows.
BLOCKS_READ = {"ship": 4, "ctl": 4, "d2": 2, "d1": 1}
CALLS_PER_STEP = 39.0


def load(d):
    runs = []
    for path in sorted(glob.glob(os.path.join(d, "run*_*.steps")),
                       key=lambda p: int(re.search(r"run(\d+)_", p).group(1))):
        m = re.search(r"run(\d+)_(\w+)\.steps$", path)
        idx, arm = int(m.group(1)), m.group(2)
        with open(path) as fh:
            vals = [float(x) for x in fh if x.strip()]
        runs.append({"idx": idx, "arm": arm, "steps": vals})
    return runs


def boot_ci(vals, nboot, stat, lo=2.5, hi=97.5, seed=118):
    rng = random.Random(seed)
    n = len(vals)
    if n == 0:
        return (float("nan"), float("nan"))
    draws = []
    for _ in range(nboot):
        draws.append(stat([vals[rng.randrange(n)] for _ in range(n)]))
    draws.sort()
    return (draws[int(lo / 100 * nboot)], draws[min(nboot - 1, int(hi / 100 * nboot))])


def bimodality(vals, nbin=48):
    """Coarse two-mode screen.  Returns (report_lines, is_bimodal)."""
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return (["  degenerate (all samples equal)"], False)
    w = (hi - lo) / nbin
    counts = [0] * nbin
    for v in vals:
        counts[min(nbin - 1, int((v - lo) / w))] += 1
    peak = max(counts)
    # find the two largest local maxima separated by a valley below 50% of both
    idx_sorted = sorted(range(nbin), key=lambda i: -counts[i])
    p1 = idx_sorted[0]
    bimodal = False
    detail = ""
    for p2 in idx_sorted[1:]:
        if abs(p2 - p1) < 4:
            continue
        if counts[p2] < 0.20 * peak:
            break
        a, b = sorted((p1, p2))
        valley = min(counts[a + 1:b]) if b > a + 1 else counts[a]
        if valley < 0.50 * min(counts[a], counts[b]):
            bimodal = True
            detail = (f"  modes at {lo + (a + .5) * w:.3f} / "
                      f"{lo + (b + .5) * w:.3f} ms, valley {valley} vs "
                      f"{min(counts[a], counts[b])}")
        break
    lines = []
    for i in range(nbin):
        if counts[i] == 0 and (i == 0 or counts[i - 1] == 0):
            continue
        bar = "#" * max(0, int(60 * counts[i] / peak))
        lines.append(f"  {lo + i * w:8.3f} |{bar} {counts[i]}")
    if detail:
        lines.append(detail)
    return (lines, bimodal)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--warmup", type=int, default=8,
                    help="per-run leading steps discarded (DVFS settle)")
    ap.add_argument("--boot", type=int, default=20000)
    ap.add_argument("--label", default=None)
    a = ap.parse_args()

    label = a.label or os.path.basename(os.path.normpath(a.dir))
    runs = load(a.dir)
    if not runs:
        raise SystemExit(f"no run*.steps under {a.dir}")

    print(f"### R118-A dose analysis -- order {label}")
    print(f"# {len(runs)} runs, warmup {a.warmup} steps/run discarded, "
          f"{a.boot} bootstrap resamples over BLOCKS\n")

    # ---- raw CSV
    csv_path = os.path.join(a.dir, f"raw-steps-{label}.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["run_idx", "arm", "block", "step_idx", "step_ms", "used"])
        for r in runs:
            blk = (r["idx"] - 1) // 4
            for si, v in enumerate(r["steps"]):
                w.writerow([r["idx"], r["arm"], blk, si, f"{v:.6f}",
                            int(si >= a.warmup)])
    n_used = sum(max(0, len(r["steps"]) - a.warmup) for r in runs)
    print(f"raw samples: {sum(len(r['steps']) for r in runs)} total, "
          f"{n_used} measured (after warmup) -> {csv_path}\n")

    # ---- per-run summary
    print("run  arm    n    median_ms   mean_ms     sd_ms")
    for r in runs:
        v = r["steps"][a.warmup:]
        print(f"{r['idx']:3d}  {r['arm']:<5s} {len(v):4d}  {st.median(v):9.4f} "
              f"{st.mean(v):9.4f} {st.pstdev(v):9.4f}")
    print()

    # ---- pooled per-arm and bimodality screen
    pooled = {arm: [] for arm in ARMS}
    for r in runs:
        pooled.setdefault(r["arm"], []).extend(r["steps"][a.warmup:])
    dead = False
    for arm in ARMS:
        v = pooled.get(arm) or []
        if not v:
            continue
        lines, bi = bimodality(v)
        print(f"arm {arm}: n={len(v)} median={st.median(v):.4f} "
              f"mean={st.mean(v):.4f} sd={st.pstdev(v):.4f} "
              f"bimodal={'YES -- INSTRUMENT FAILURE' if bi else 'no'}")
        for ln in lines:
            print(ln)
        print()
        dead = dead or bi

    # ---- paired block contrasts vs ship
    blocks = {}
    for r in runs:
        blocks.setdefault((r["idx"] - 1) // 4, {})[r["arm"]] = \
            st.median(r["steps"][a.warmup:])
    good = [b for b in sorted(blocks) if set(blocks[b]) >= set(ARMS)]
    print(f"complete blocks: {len(good)} of {len(blocks)}\n")

    print("PAIRED SAVING vs ship  (positive = arm is FASTER than ship), ms/step")
    print("arm    nblk   median      mean       95% CI (median, block bootstrap)"
          "        excl 0?")
    results = {}
    for arm in ARMS[1:]:
        d = [blocks[b]["ship"] - blocks[b][arm] for b in good]
        if not d:
            continue
        lo, hi = boot_ci(d, a.boot, st.median)
        excl = "YES" if (lo > 0 or hi < 0) else "no"
        results[arm] = (st.median(d), st.mean(d), lo, hi)
        print(f"{arm:<5s} {len(d):5d} {st.median(d):9.4f} {st.mean(d):9.4f}   "
              f"[{lo:+8.4f}, {hi:+8.4f}]   {excl}")
    print()

    # ---- verdicts
    if "ctl" in results:
        _, _, lo, hi = results["ctl"]
        if lo > 0 or hi < 0:
            print("!! NEGATIVE CONTROL FAILED: the byte-identical arm differs "
                  "from ship at 95%.")
            print("!! Per the R118-A method this is a rig report, not a "
                  "kernel result.  STOP.")
            dead = True
        else:
            print(f"negative control OK: ctl interval [{lo:+.4f}, {hi:+.4f}] "
                  f"ms/step contains zero.")
    if dead:
        print("\nVERDICT: instrument failure -- see above.")
        return

    # ---- byte-response fit  t_call = c + nblocks * m
    if "d2" in results and "d1" in results:
        s2, s1 = results["d2"][0], results["d1"][0]     # ms/step saved
        # per-call microseconds saved
        u2, u1 = s2 * 1e3 / CALLS_PER_STEP, s1 * 1e3 / CALLS_PER_STEP
        # ship reads 4 blocks; d2 reads 2 (saves 2), d1 reads 1 (saves 3)
        m2 = u2 / 2.0
        m1 = u1 / 3.0
        # least-squares slope through (4, T4), (2, T4-u2), (1, T4-u1)
        xs = [4.0, 2.0, 1.0]
        ys = [0.0, -u2, -u1]        # relative to ship
        xb, yb = sum(xs) / 3, sum(ys) / 3
        slope = sum((x - xb) * (y - yb) for x, y in zip(xs, ys)) / \
            sum((x - xb) ** 2 for x in xs)
        print("\nBYTE-RESPONSE FIT  t_call(nblocks) = c + nblocks * m")
        print(f"  per-call saving  d2 (-2 blocks): {u2:8.4f} us  "
              f"-> m = {m2:7.4f} us/block")
        print(f"  per-call saving  d1 (-3 blocks): {u1:8.4f} us  "
              f"-> m = {m1:7.4f} us/block")
        print(f"  LS slope m = {slope:.4f} us/block")
        # each K block = 1024 rows * 128 packed bytes + 1024 * 16 scale bytes
        mb_per_block = (1024 * 128 + 1024 * 16) / 1e6
        if slope > 0:
            print(f"  block moves {mb_per_block:.4f} MB unique -> "
                  f"marginal rate {mb_per_block / (slope * 1e-6) / 1e9:.1f} GB/s")
        print("  reference: 225 GB/s measured streaming ceiling for a ~1.2 MB "
              "dispatch (R110 F2);")
        print("             159 GB/s is this kernel's own in-situ average rate.")


if __name__ == "__main__":
    main()
