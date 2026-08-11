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

SHARED_ARMS = ["ship", "ctl", "d2", "d1"]
ROUTED_ARMS = ["ship", "rctl", "rd2", "rd1"]
# K blocks each arm actually reads.  Both kernels run a 4-block K loop; the
# dose truncates the loop bound, so d2/rd2 read 2 blocks and d1/rd1 read 1.
BLOCKS_READ = {"ship": 4, "ctl": 4, "d2": 2, "d1": 1,
               "rctl": 4, "rd2": 2, "rd1": 1}
# unique weight+scale bytes one K block moves, per decode step, from PREREG.md
MB_PER_BLOCK_STEP = {"shared": 10.86, "routed": 86.9}
CALLS_PER_STEP = 39.0
# Rule 105.12 landing bar, expressed on this M4 Pro: +30 us/step of M5 wall
# is +68.7 us/step here (0.251 % of score at tau = 1).
BAR_US_STEP = 68.7


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


def _pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, max(0, int(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def bimodality(vals, nbin=40):
    """Two-mode screen on the pooled per-step samples.

    The R118-A method note says a bimodal step-time distribution means the
    instrument (or the machine) is switching states and the run must be thrown
    away.  What it does NOT mean is "the histogram has a sparse bin in it", so
    the test is deliberately conservative and must clear four hurdles at once:

      1. two smoothed local maxima, each holding >= 10 % of the peak height;
      2. separated by >= 5 bins;
      3. with a valley between them below 35 % of the smaller peak;
      4. the two clusters separated by >= 3 robust sigma (1.4826 * MAD) AND
         each side of the valley holding >= 15 % of the samples.

    Returns (report_lines, is_bimodal).
    """
    sv = sorted(vals)
    n = len(sv)
    med = st.median(sv)
    mad = st.median([abs(v - med) for v in sv]) or 1e-9
    sigma = 1.4826 * mad
    lo, hi = _pct(sv, 0.005), _pct(sv, 0.995)   # trim so tails do not squash
    if hi <= lo:
        return (["  degenerate (all samples equal)"], False)
    w = (hi - lo) / nbin
    counts = [0] * nbin
    out = 0
    for v in sv:
        if v < lo or v > hi:
            out += 1
            continue
        counts[min(nbin - 1, int((v - lo) / w))] += 1
    sm = [sum(counts[max(0, i - 1):i + 2]) / 3.0 for i in range(nbin)]
    peak = max(sm)

    bimodal, detail = False, ""
    peaks = [i for i in range(1, nbin - 1)
             if sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1] and sm[i] >= 0.10 * peak]
    peaks.sort(key=lambda i: -sm[i])
    for j, p2 in enumerate(peaks):
        for p1 in peaks[:j]:
            if abs(p2 - p1) < 5:
                continue
            a, b = sorted((p1, p2))
            valley_i = min(range(a + 1, b), key=lambda i: sm[i])
            valley = sm[valley_i]
            if valley >= 0.35 * min(sm[a], sm[b]):
                continue
            cut = lo + (valley_i + 0.5) * w
            left = sum(1 for v in sv if v < cut)
            if min(left, n - left) < 0.15 * n:
                continue
            if abs((lo + (b + .5) * w) - (lo + (a + .5) * w)) < 3 * sigma:
                continue
            bimodal = True
            detail = (f"  BIMODAL: modes at {lo + (a + .5) * w:.4f} / "
                      f"{lo + (b + .5) * w:.4f} ms (sep "
                      f"{((b - a) * w) / sigma:.1f} sigma), valley "
                      f"{valley:.1f} vs {min(sm[a], sm[b]):.1f}, mass split "
                      f"{left}/{n - left}")
            break
        if bimodal:
            break

    lines = []
    for i in range(nbin):
        if counts[i] == 0 and (i == 0 or counts[i - 1] == 0):
            continue
        bar = "#" * max(0, int(60 * counts[i] / max(counts)))
        lines.append(f"  {lo + i * w:8.4f} |{bar} {counts[i]}")
    if out:
        lines.append(f"  ({out} samples outside the 0.5-99.5 pct histogram "
                     f"range, kept in every statistic)")
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

    seen = {r["arm"] for r in runs}
    if seen & set(ROUTED_ARMS[1:]):
        ARMS, family, ctl_arm = ROUTED_ARMS, "routed", "rctl"
    else:
        ARMS, family, ctl_arm = SHARED_ARMS, "shared", "ctl"
    mb_blk = MB_PER_BLOCK_STEP[family]
    print(f"# kernel family: {family} gate+up QMV; arms {ARMS}; "
          f"one K block = {mb_blk} MB/step")

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
    if len(good) < 3:
        print(f"NOTE: only {len(good)} complete block(s) -- the block "
              f"bootstrap is degenerate here and no")
        print("      interval below may be quoted.  This is a shakedown "
              "directory, not a campaign order.")
        return
    if ctl_arm in results:
        _, _, lo, hi = results[ctl_arm]
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

    # ---- byte-response fit  t_step(nblocks) = c + nblocks * k * MB_per_block
    a2, a1 = ARMS[2], ARMS[3]
    if a2 in results and a1 in results:
        s2, s1 = results[a2][0], results[a1][0]         # ms/step saved
        u2, u1 = s2 * 1e3, s1 * 1e3                     # us/step saved
        # ship reads 4 blocks; *d2 reads 2 (removes 2 blocks), *d1 reads 1 (3)
        mb2, mb1 = 2 * mb_blk, 3 * mb_blk
        print("\nBYTE-RESPONSE FIT   saving(us/step) = k * MB removed/step")
        print(f"  {a2}: -{mb2:6.2f} MB/step -> {u2:+8.2f} us/step  "
              f"=> k = {u2 / mb2:+7.3f} us per MB/step")
        print(f"  {a1}: -{mb1:6.2f} MB/step -> {u1:+8.2f} us/step  "
              f"=> k = {u1 / mb1:+7.3f} us per MB/step")
        # least-squares slope through the three points (0,0), (mb2,u2), (mb1,u1)
        xs, ys = [0.0, mb2, mb1], [0.0, u2, u1]
        xb, yb = sum(xs) / 3, sum(ys) / 3
        k = sum((x - xb) * (y - yb) for x, y in zip(xs, ys)) / \
            sum((x - xb) ** 2 for x in xs)
        print(f"  LS slope k = {k:+.4f} us of decode wall per MB/step removed")
        if k > 0:
            print(f"             = {1.0 / k * 1e3:.0f} GB/s marginal "
                  f"streaming rate")
        print("  smoke calibration on the routed family: k = +2.61 us per "
              "MB/step (383 GB/s marginal).")
        if family == "shared":
            print(f"  byte model would predict {2.61 * mb2:.0f} us ({a2}) and "
                  f"{2.61 * mb1:.0f} us ({a1}) at that k.")

        # ---- the pre-registered decision rule, applied verbatim
        print("\nDECISION RULE (pre-registered in PREREG.md, "
              "before any of this data existed)")
        if family == "shared":
            hi1 = results[a1][3]
            print(f"  d1 removes 75 % of this kernel's weight traffic -- more "
                  f"than any correct")
            print(f"  rewrite could ever remove -- and its 95 % upper bound on "
                  f"the saving is")
            print(f"  {hi1 * 1e3:+.1f} us/step against a landing bar of "
                  f"{BAR_US_STEP:.1f} us/step.")
            if hi1 * 1e3 < BAR_US_STEP:
                print("  => TERMINAL NEGATIVE on the byte side of this target: "
                      "even deleting three")
                print("     quarters of the reads cannot reach the bar.  "
                      "Do not land; publish the law.")
            else:
                print("  => the byte side is NOT closed by this test; report "
                      "the interval and the")
                print("     fraction of the 68 us/step excess it would "
                      "actually recover.")


if __name__ == "__main__":
    main()
