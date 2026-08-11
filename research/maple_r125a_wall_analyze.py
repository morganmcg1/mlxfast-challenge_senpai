#!/usr/bin/env python3
"""Analyse the R125-A SPLIT=0 paired wall A/B (research/maple_r125a_wall.sh).

Reports steady-tail wall microseconds per decode step for each slot, the paired
within-block TG256-minus-TG64 delta, and a bootstrap CI over blocks.
"""
import argparse
import glob
import os
import random
import re
import statistics as st

SLOT_RE = re.compile(r"b(\d+)_s(\d+)_tg(\d+)\.steps$")


def tail_mean_us(path, drop, stat="mean"):
    vals = [float(x) for x in open(path) if x.strip()]
    tail = vals[drop:]
    centre = st.median(tail) if stat == "median" else st.mean(tail)
    return 1000.0 * centre, 1000.0 * st.stdev(tail), len(tail)


def collect(outdir, drop=16, stat="mean"):
    slots = {}
    for path in sorted(glob.glob(os.path.join(outdir, "b*_s*_tg*.steps"))):
        m = SLOT_RE.search(os.path.basename(path))
        b, s, tg = int(m.group(1)), int(m.group(2)), int(m.group(3))
        mean, sd, n = tail_mean_us(path, drop, stat)
        slots[(b, s)] = (tg, mean, sd, n)
    return slots


def paired_deltas(slots):
    out = []
    for b in sorted({b for (b, _) in slots}):
        a = [slots[(b, s)][1] for s in (1, 4) if (b, s) in slots]
        c = [slots[(b, s)][1] for s in (2, 3) if (b, s) in slots]
        if len(a) == 2 and len(c) == 2:
            out.append((b, st.mean(a), st.mean(c), st.mean(c) - st.mean(a)))
    return out


def slot_pair_deltas(slots):
    """Mirror-pair deltas: (s2 - s1) and (s3 - s4) inside each block.

    Twice as many paired observations as `paired_deltas`, each spanning a
    shorter stretch of wall clock, so slow drift cancels within the pair.
    """
    out = []
    for b in sorted({b for (b, _) in slots}):
        for hot, cold in ((2, 1), (3, 4)):
            if (b, hot) in slots and (b, cold) in slots:
                out.append((b, f"s{hot}-s{cold}",
                            slots[(b, hot)][1] - slots[(b, cold)][1]))
    return out


def bootstrap_ci(deltas, seed=20260810, draws=20000):
    random.seed(seed)
    boot = sorted(st.mean(random.choices(deltas, k=len(deltas)))
                  for _ in range(draws))
    return boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]


def wandb_summary(outdir, drop=16, stat="mean"):
    slots = collect(outdir, drop, stat)
    rows = paired_deltas(slots)
    if len(rows) < 2:
        return {}
    d = [r[3] for r in rows]
    lo, hi = bootstrap_ci(d)
    sp = [r[2] for r in slot_pair_deltas(slots)]
    sp_lo, sp_hi = bootstrap_ci(sp)
    tg64 = st.mean([v[1] for v in slots.values() if v[0] == 64])
    tg256 = st.mean([v[1] for v in slots.values() if v[0] == 256])
    mu = st.mean(d)
    return {
        "wall/pair_delta_us_per_step": st.mean(sp),
        "wall/pair_delta_sem": st.stdev(sp) / len(sp) ** 0.5,
        "wall/pair_delta_ci95_lo": sp_lo,
        "wall/pair_delta_ci95_hi": sp_hi,
        "wall/pairs": len(sp),
        "wall/pairs_positive": sum(1 for x in sp if x > 0),
        "wall/tg64_us_per_step": tg64,
        "wall/tg256_us_per_step": tg256,
        "wall/delta_us_per_step": mu,
        "wall/delta_sem": st.stdev(d) / len(d) ** 0.5,
        "wall/delta_ci95_lo": lo,
        "wall/delta_ci95_hi": hi,
        "wall/delta_pct": 100 * mu / tg64,
        "wall/blocks": len(d),
        "wall/blocks_positive": sum(1 for x in d if x > 0),
        "wall/steady_tail_drop": drop,
        "wall/slots": len(slots),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/maple-r125a-wall")
    ap.add_argument("--drop", type=int, default=16,
                    help="steps discarded as the non-steady head")
    ap.add_argument("--stat", choices=("mean", "median"), default="mean",
                    help="per-slot centre; median is robust to OS hiccup steps")
    args = ap.parse_args()

    slots = collect(args.out, args.drop, args.stat)

    print(f"# steady tail: steps >= {args.drop}, centre={args.stat}")
    print(f"{'block':>5} {'slot':>4} {'TG':>4} {'us/step':>10} {'sd':>8} {'n':>5}")
    for (b, s) in sorted(slots):
        tg, mean, sd, n = slots[(b, s)]
        print(f"{b:5d} {s:4d} {tg:4d} {mean:10.2f} {sd:8.2f} {n:5d}")

    rows = paired_deltas(slots)
    for b, a, c, d in rows:
        print(f"block {b}: tg64={a:.2f}  tg256={c:.2f}  delta={d:+.2f} us/step")

    if len(rows) < 2:
        print("insufficient complete blocks")
        return

    s = wandb_summary(args.out, args.drop, args.stat)
    print(f"\narm mean tg64 : {s['wall/tg64_us_per_step']:.2f} us/step")
    print(f"arm mean tg256: {s['wall/tg256_us_per_step']:.2f} us/step")
    print(f"paired delta  : {s['wall/delta_us_per_step']:+.2f} +/- "
          f"{s['wall/delta_sem']:.2f} us/step CI95 "
          f"[{s['wall/delta_ci95_lo']:+.2f}, {s['wall/delta_ci95_hi']:+.2f}]  "
          f"({s['wall/delta_pct']:+.3f} %)")
    print(f"blocks positive: {s['wall/blocks_positive']}/{s['wall/blocks']}")
    for b, tag, d in slot_pair_deltas(slots):
        print(f"  pair b{b} {tag}: {d:+.2f} us/step")
    print(f"mirror-pair delta: {s['wall/pair_delta_us_per_step']:+.2f} +/- "
          f"{s['wall/pair_delta_sem']:.2f} us/step CI95 "
          f"[{s['wall/pair_delta_ci95_lo']:+.2f}, "
          f"{s['wall/pair_delta_ci95_hi']:+.2f}]  "
          f"({s['wall/pairs_positive']}/{s['wall/pairs']} positive)")
    # A +0.38 % score claim on a decode-only change needs decode step time to
    # fall by 1 - 1.0038^(1/0.75) = 0.504 %.
    need = -0.00504 * s["wall/tg64_us_per_step"]
    print(f"advisor's +0.38 % score claim requires delta = {need:+.1f} us/step")


if __name__ == "__main__":
    main()
