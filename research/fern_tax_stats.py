#!/usr/bin/env python3
"""Research-only reducer for research/fern_tax_probe.py output (PR #268).

ONE reducer, one convention.  PR #241 shipped two that disagreed by ~6%
(fern_gap_stats.py centred every contrast on the K=1 arm, fern_gap_wandb.py
centred on the block mean).  This file uses exactly one estimator and every
number in the deliverable comes from it:

  WITHIN-BLOCK (FIXED-EFFECTS) OLS ON SEGMENT MEDIANS.

  * unit of replication  = one segment median (steps < --drop discarded)
  * the palindromic schedule is repeated `blocks` times; a block is one
    full pass of the schedule
  * both the regressor x and the response y are centred on their own
    BLOCK MEAN before the slope is formed, so any linear thermal/clock
    drift inside a block cancels and no single arm acts as the reference
  * the reported CI is the classical OLS t interval on the within-block
    residual degrees of freedom (n_segments - n_blocks - 1)

The regressor is chosen with --x:
  k          nominal injected dispatch groups per step (schedule value)
  dispatch   MEASURED dispatch count/step from the device.cpp counters
  barrier    MEASURED memoryBarrier count/step
  spin_us    nominal injected CPU busy-spin microseconds per step

Preferring x=dispatch over x=k is the whole point of the counter
instrument: it prices a real dispatch, not an intended one.

The response is chosen with --y (all reported in us/step):
  ms         wall clock per decode step (the thing that scores)
  gpu_ms     GPUStartTime->GPUEndTime summed over the step's command buffers
  span_ms    commit->completion span
  gap_ms     span_ms - gpu_ms, time inside the span with the GPU not busy
  kernel_ms  kernelStartTime->kernelEndTime, the CPU driver's own work

y=gpu_ms against y=gap_ms is the E1-vs-E2 decomposition: injected work that
shows up in gpu_ms is GPU-paced, work that shows up in gap_ms is CPU-paced.

Passing several TSVs pools them with a (file, block) fixed effect and prints
each arm's own slope beside the pooled line.  An arm that sits off the pooled
line falsifies that regressor for that family of arms.

  python3 research/fern_tax_stats.py /tmp/fern268/chain40.tsv --x dispatch
  python3 research/fern_tax_stats.py /tmp/fern268/{chain40,fat40_8k,fan40}.tsv \\
      --x barrier
"""
import argparse
import math
import statistics
from collections import defaultdict

# From the assignment's frozen score model -- do not re-derive.
PERCENT_PER_US_DECODE = 0.015280   # % of score per us/step on M5
M5_STEP_MS = 4.143569
M5_DECODE_SIGMA_US = 15.34         # cross-session decode sigma, us/step
N_LAYERS = 40                      # weights/config.json num_hidden_layers

UNIT = {"k": "per K", "dispatch": "per dispatch", "barrier": "per barrier",
        "spin_us": "per injected CPU us"}


def t95(df):
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
             20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000,
             120: 1.980}
    for k in sorted(table):
        if df <= k:
            return table[k]
    return 1.96


def read_timing(path):
    meta, rows, drop = {}, [], 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                for tok in line.lstrip("# ").split():
                    if "=" in tok:
                        a, b = tok.split("=", 1)
                        meta[a] = b
                drop = int(meta.get("drop", 0))
                continue
            if line.startswith("segment"):
                continue
            seg, k, step, ms = line.split()
            if step.isdigit() and int(step) >= drop:
                rows.append((int(seg), int(k), float(ms)))
    return meta, rows


def read_counters(path):
    out = {}
    try:
        fh = open(path)
    except OSError:
        return out
    with fh:
        head = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            rec = dict(zip(head, parts))
            out[int(rec["segment"])] = {k: float(v) for k, v in rec.items()
                                        if k != "segment"}
    return out


def block_length(seg_k, segs):
    ks = [seg_k[s] for s in segs]
    for n in range(2, len(segs) + 1):
        if len(segs) % n == 0 and all(ks[i] == ks[i % n]
                                      for i in range(len(ks))):
            return n
    return len(segs)


def fe_ols(points, n_blocks):
    """points: list of (block, x, y).  Returns slope, se, df, n."""
    by_block = defaultdict(list)
    for b, x, y in points:
        by_block[b].append((x, y))
    sxx = sxy = 0.0
    centred = []
    for b, pts in by_block.items():
        xb = statistics.mean(p[0] for p in pts)
        yb = statistics.mean(p[1] for p in pts)
        for x, y in pts:
            cx, cy = x - xb, y - yb
            sxx += cx * cx
            sxy += cx * cy
            centred.append((cx, cy))
    if sxx == 0:
        return float("nan"), float("nan"), 0, len(points)
    slope = sxy / sxx
    df = len(points) - n_blocks - 1
    if df <= 0:
        return slope, float("nan"), 0, len(points)
    ssr = sum((cy - slope * cx) ** 2 for cx, cy in centred)
    se = math.sqrt(ssr / df / sxx)
    return slope, se, df, len(points)


def fe_ols2(points, n_blocks):
    """points: (block, x1, x2, y).  Returns (b1,se1), (b2,se2), df, n.

    Dispatch count and barrier count are collinear in any single arm, so the
    only way to price them apart is to pool arms whose barrier-per-dispatch
    ratio differs (chain40=1, fat40=1, fan40 falls to 0 between K=2 and K=4).
    """
    by_block = defaultdict(list)
    for b, x1, x2, y in points:
        by_block[b].append((x1, x2, y))
    s11 = s22 = s12 = s1y = s2y = 0.0
    centred = []
    for pts in by_block.values():
        m1 = statistics.mean(p[0] for p in pts)
        m2 = statistics.mean(p[1] for p in pts)
        my = statistics.mean(p[2] for p in pts)
        for x1, x2, y in pts:
            c1, c2, cy = x1 - m1, x2 - m2, y - my
            s11 += c1 * c1
            s22 += c2 * c2
            s12 += c1 * c2
            s1y += c1 * cy
            s2y += c2 * cy
            centred.append((c1, c2, cy))
    nan, n = float("nan"), len(points)
    det = s11 * s22 - s12 * s12
    if det == 0:
        return (nan, nan), (nan, nan), 0, n
    b1 = (s22 * s1y - s12 * s2y) / det
    b2 = (s11 * s2y - s12 * s1y) / det
    df = n - n_blocks - 2
    if df <= 0:
        return (b1, nan), (b2, nan), 0, n
    ssr = sum((cy - b1 * c1 - b2 * c2) ** 2 for c1, c2, cy in centred)
    s2 = ssr / df
    return ((b1, math.sqrt(s2 * s22 / det)),
            (b2, math.sqrt(s2 * s11 / det)), df, n)


def joint_points(path):
    """[(block, dispatch, barrier, wall_us)] for the joint fit."""
    meta, rows = read_timing(path)
    ctr = read_counters(path + ".ctr.tsv")
    seg_k, per_seg = {}, defaultdict(list)
    for seg, k, ms in rows:
        seg_k[seg] = k
        per_seg[seg].append(ms)
    segs = sorted(per_seg)
    med = {s: statistics.median(per_seg[s]) for s in segs}
    blen = block_length(seg_k, segs)
    return [(i // blen, ctr[s]["dispatch"], ctr[s]["barrier"], med[s] * 1e3)
            for i, s in enumerate(segs) if s in ctr]


def project_m5(slope, half, baseline_ms):
    """Print the M5 transfer band for removing dispatches from the live path.

    This host is not the ranked host, so report both ends of the transfer
    assumption instead of pretending one of them is the answer: 1:1 (the
    cost is fixed overhead, upper bound) and step-time scaled (the cost
    shrinks with the machine, lower bound).
    """
    print(f"  -> measured refund of removing ONE from the live chain on THIS "
          f"host: {slope:.3f} us [{slope-half:.3f}, {slope+half:.3f}]")
    ratio = M5_STEP_MS / (baseline_ms or M5_STEP_MS)
    print(f"     M5 transfer band: 1.000x (fixed overhead) to "
          f"{ratio:.3f}x (scales with step time)")
    print(f"     {'removed per step':34s} {'us/step':>18} "
          f"{'% score':>15} {'sigma':>13}")
    for n_unit, tag in ((1, f"1 per layer (x{N_LAYERS})"),
                        (3, f"3 per layer (x{N_LAYERS})"),
                        (10, f"10 per layer (x{N_LAYERS})")):
        hi = slope * n_unit * N_LAYERS
        lo = hi * ratio
        print(f"     {tag:34s} {lo:8.1f}..{hi:-8.1f} "
              f"{lo*PERCENT_PER_US_DECODE:6.3f}..{hi*PERCENT_PER_US_DECODE:-6.3f} "
              f"{lo/M5_DECODE_SIGMA_US:5.2f}..{hi/M5_DECODE_SIGMA_US:-5.2f}")


def axes(meta, seg_k, med, ctr, x_kind, y_kind):
    """Return (xval, yval) segment accessors.  Both are in microseconds/step
    where they are times, so every slope reads as us/step per unit of x."""
    spin_ns = float(meta.get("spin_ns", 0))

    def xval(s):
        if x_kind == "k":
            return float(seg_k[s])
        if x_kind == "spin_us":
            return seg_k[s] * 40 * spin_ns / 1e3
        c = ctr.get(s)
        if c is None:
            raise SystemExit(f"segment {s} has no counters; use --x k")
        return c[x_kind]

    def yval(s):
        if y_kind == "ms":
            return med[s] * 1e3
        c = ctr.get(s)
        if c is None:
            raise SystemExit(f"segment {s} has no counters; use --y ms")
        if y_kind == "gap_ms":
            return (c["span_ns"] - c["gpu_ns"]) / 1e3
        return c[y_kind.replace("_ms", "_ns")] / 1e3

    return xval, yval


def fit(path, x_kind, y_kind="ms"):
    """Non-printing single-arm reduction, for the W&B logger.

    Uses exactly the same accessors, blocking and estimator as analyze(),
    so the logged numbers cannot drift from the deliverable's numbers.
    """
    meta, rows = read_timing(path)
    ctr = read_counters(path + ".ctr.tsv")
    seg_k, per_seg = {}, defaultdict(list)
    for seg, k, ms in rows:
        seg_k[seg] = k
        per_seg[seg].append(ms)
    segs = sorted(per_seg)
    if not segs or (x_kind not in ("k", "spin_us") and not ctr):
        return None
    med = {s: statistics.median(per_seg[s]) for s in segs}
    blen = block_length(seg_k, segs)
    n_blocks = len(segs) // blen
    xval, yval = axes(meta, seg_k, med, ctr, x_kind, y_kind)
    pts = [(i // blen, xval(s), yval(s)) for i, s in enumerate(segs)]
    slope, se, df, n = fe_ols(pts, n_blocks)
    half = t95(df) * se if se == se else float("nan")
    kmin = min(seg_k.values())
    base = [s for s in segs if seg_k[s] == kmin]
    out = {"meta": meta, "x": x_kind, "y": y_kind, "slope_us": slope,
           "se_us": se, "ci95_half_us": half, "df": df, "n_points": n,
           "blocks": n_blocks, "block_len": blen,
           "baseline_ms": statistics.mean(med[s] for s in base)}
    bc = [ctr[s] for s in base if s in ctr]
    if bc:
        for key in ("dispatch", "barrier", "commit", "encode"):
            out["baseline_" + key] = statistics.mean(c[key] for c in bc)
        for key in ("gpu", "kernel", "span"):
            out["baseline_" + key + "_ms"] = statistics.mean(
                c[key + "_ns"] for c in bc) / 1e6
        out["baseline_gpu_busy_frac"] = (out["baseline_gpu_ms"]
                                         / out["baseline_ms"])
    return out


def analyze(path, args):
    """Reduce one arm.  Returns (label, baseline_ms, points) for pooling."""
    meta, rows = read_timing(path)
    ctr = read_counters(path + ".ctr.tsv")

    seg_k, per_seg = {}, defaultdict(list)
    for seg, k, ms in rows:
        seg_k[seg] = k
        per_seg[seg].append(ms)
    segs = sorted(per_seg)
    med = {s: statistics.median(per_seg[s]) for s in segs}
    blen = block_length(seg_k, segs)
    n_blocks = len(segs) // blen
    arms = sorted({seg_k[s] for s in segs})
    xval, yval = axes(meta, seg_k, med, ctr, args.x, args.y)

    label = args.label or path.rsplit("/", 1)[-1].replace(".tsv", "")
    print(f"== {label}  mode={meta.get('mode')} bytes={meta.get('bytes')} "
          f"pool={meta.get('pool')} anchor={meta.get('anchor')} "
          f"x={args.x} y={args.y} ==")
    print(f"   {len(segs)} segments, block={blen}, blocks={n_blocks}, "
          f"arms={arms}, timed steps/seg={len(per_seg[segs[0]])}, "
          f"divergences={meta.get('divergences')}")

    if not ctr:
        print("   WARNING: no counter file; only x=k / x=spin_us are usable")

    # ---- per-arm table (means over segments sharing the same K) -----------
    print(f"\n{'K':>5} {'x':>10} {'ms':>9} {'d_us_vs_min':>12} "
          f"{'disp':>8} {'barr':>8} {'commit':>7} {'gpu_ms':>8} "
          f"{'kern_ms':>8} {'span_ms':>8} {'gpu/wall':>9}")
    arm_ms, arm_x = {}, {}
    for k in arms:
        ss = [s for s in segs if seg_k[s] == k]
        arm_ms[k] = statistics.mean(med[s] for s in ss)
        arm_x[k] = statistics.mean(xval(s) for s in ss)
    ref = arm_ms[min(arms)]
    for k in arms:
        ss = [s for s in segs if seg_k[s] == k]
        c = [ctr[s] for s in ss if s in ctr]
        g = statistics.mean(x["gpu_ns"] for x in c) / 1e6 if c else float("nan")
        kn = statistics.mean(x["kernel_ns"] for x in c) / 1e6 if c else float("nan")
        sp = statistics.mean(x["span_ns"] for x in c) / 1e6 if c else float("nan")
        d = statistics.mean(x["dispatch"] for x in c) if c else float("nan")
        b = statistics.mean(x["barrier"] for x in c) if c else float("nan")
        cm = statistics.mean(x["commit"] for x in c) if c else float("nan")
        print(f"{k:5d} {arm_x[k]:10.1f} {arm_ms[k]:9.4f} "
              f"{(arm_ms[k]-ref)*1e3:12.1f} {d:8.0f} {b:8.0f} {cm:7.0f} "
              f"{g:8.3f} {kn:8.3f} {sp:8.3f} {g/arm_ms[k]:9.3f}")

    # ---- the single estimator --------------------------------------------
    pts = [(i // blen, xval(s), yval(s)) for i, s in enumerate(segs)]
    slope, se, df, n = fe_ols(pts, n_blocks)
    half = t95(df) * se if se == se else float("nan")
    unit = UNIT[args.x]
    print(f"\nFE-OLS within block: {slope:+.4f} +/- {se:.4f} us/step {unit}"
          f"   (t={slope/se:+.1f}, df={df}, n={n})")
    print(f"  95% CI [{slope-half:+.4f}, {slope+half:+.4f}] us {unit}")

    baseline_ms = arm_ms[min(arms)]
    if args.x in ("dispatch", "barrier") and args.y == "ms":
        project_m5(slope, half, baseline_ms)
    if args.x == "spin_us":
        print("  slope ~1 => CPU-paced (E1 encode starvation); "
              "slope ~0 => GPU-paced")

    if args.tsv_out:
        with open(args.tsv_out, "a") as fh:
            fh.write(f"{label}\t{meta.get('mode')}\t{meta.get('bytes')}\t"
                     f"{meta.get('pool')}\t{meta.get('anchor')}\t{args.x}\t"
                     f"{args.y}\t{slope:.5f}\t{se:.5f}\t{half:.5f}\t{df}\t"
                     f"{n}\t{meta.get('divergences')}\n")
    return label, baseline_ms, pts


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tsv", nargs="+", help="probe TSV(s); >1 pools them")
    ap.add_argument("--x", default="dispatch",
                    choices=["k", "dispatch", "barrier", "spin_us"])
    ap.add_argument("--y", default="ms",
                    choices=["ms", "gpu_ms", "kernel_ms", "span_ms", "gap_ms"],
                    help="response: wall (ms), GPU busy, CPU driver (kernel), "
                         "commit->complete span, or span-minus-busy gap")
    ap.add_argument("--label", default=None,
                    help="override arm label (single-file use only)")
    ap.add_argument("--tsv-out", default=None,
                    help="append one summary row per arm to this TSV")
    ap.add_argument("--joint", action="store_true",
                    help="price dispatch and barrier together in one fit "
                         "(needs >=2 arms with different barriers/dispatch)")
    return ap


def joint(paths):
    pooled = []
    for fi, p in enumerate(paths):
        for b, d, x, y in joint_points(p):
            pooled.append(((fi, b), d, x, y))
    nb = len({p[0] for p in pooled})
    (bd, sd), (bb, sb), df, n = fe_ols2(pooled, nb)
    t = t95(df)
    names = ", ".join(p.rsplit("/", 1)[-1].replace(".tsv", "") for p in paths)
    print(f"\n== JOINT ({names}) wall_us ~ dispatch + barrier ==")
    print(f"  dispatch  {bd:+.4f} +/- {sd:.4f}  "
          f"95% CI [{bd-t*sd:+.4f}, {bd+t*sd:+.4f}]  t={bd/sd:+.1f}")
    print(f"  barrier   {bb:+.4f} +/- {sb:.4f}  "
          f"95% CI [{bb-t*sb:+.4f}, {bb+t*sb:+.4f}]  t={bb/sb:+.1f}")
    print(f"  df={df}, n={n}, blocks={nb}")
    print("  a barrier-free dispatch costs the 'dispatch' row; removing a "
          "dependent\n  edge as well refunds dispatch+barrier")
    return bd, sd, bb, sb, df, n


def main():
    args = build_parser().parse_args()
    if len(args.tsv) > 1 and args.label:
        raise SystemExit("--label is only meaningful with a single TSV")
    if args.joint:
        joint(args.tsv)
        return 0
    results = [analyze(p, args) for p in args.tsv]
    if len(results) < 2:
        return 0

    # ---- pooled estimate across arms -------------------------------------
    # The fixed effect is (file, block): pooling asks whether ONE slope in x
    # explains all arms at once.  If x=barrier fits several arms with one
    # slope while x=dispatch does not, the tax is a barrier cost, not a
    # dispatch cost.
    pooled, base = [], []
    for fi, (label, baseline_ms, pts) in enumerate(results):
        base.append(baseline_ms)
        for b, x, y in pts:
            pooled.append(((fi, b), x, y))
    nb = len({p[0] for p in pooled})
    slope, se, df, n = fe_ols(pooled, nb)
    half = t95(df) * se if se == se else float("nan")
    labels = ", ".join(r[0] for r in results)
    print(f"\n== POOLED ({labels}) x={args.x} y={args.y} ==")
    print(f"FE-OLS within (file,block): {slope:+.4f} +/- {se:.4f} us/step "
          f"{UNIT[args.x]}   (t={slope/se:+.1f}, df={df}, n={n}, blocks={nb})")
    print(f"  95% CI [{slope-half:+.4f}, {slope+half:+.4f}]")
    # Residual scatter of the pooled fit vs the per-arm fits is the
    # discrimination: a good regressor leaves the arms on one line.
    for label, _, pts in results:
        s2, se2, df2, _ = fe_ols(pts, len({p[0] for p in pts}))
        h2 = t95(df2) * se2 if se2 == se2 else float("nan")
        flag = "" if abs(s2 - slope) <= h2 + half else "   <-- OFF THE LINE"
        print(f"    {label:18s} {s2:+.4f} +/- {h2:.4f}{flag}")
    if args.x in ("dispatch", "barrier") and args.y == "ms":
        project_m5(slope, half, statistics.mean(base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
