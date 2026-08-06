#!/usr/bin/env python3
"""Close the 512-token prefill budget against M5 ceilings and report the
explicit UNATTRIBUTED residual.

Why this is not done by converting M4 microseconds: 94.3% of measured M4
prefill GPU time sits in kernels whose M5 twin is a different `_nax` kernel
that this host cannot select (research/pr91-logs/step2-census-split1.log +
`nax_gen_required=17 nax_available=false`). Applying the campaign's
decode-derived conversion factors to the M4 families overshoots the M5 forward
by ~2.4x. So each family floor is derived from A-column bytes and FLOPs
divided by M5 machine ceilings, and the gap to the measured M5 forward is
carried as one honest UNATTRIBUTED row.

Divisor note: 610 GB/s is DEFINITIONAL (`1794 MB / 2.941 ms`) and
research/CURRENT_RESEARCH_STATE.md:600 restricts it to the decode roofline
ledger, stating it "is not a physical capability and must never be quoted as
one". It is reported here only as the optimistic end of a band whose other
members are the measured routed-plane rate (546.2 GB/s,
CURRENT_RESEARCH_STATE.md:602) and research/prefill_ridge.py's stated M5
achievable ceilings (485 / 500 / 530 GB/s).
"""
import argparse

# research/pr91-logs/step2-budget-m4.log, itself derived by
# research/prefill_budget.py from LagunaConstants geometry + observed shapes.
# (weight GB, activation GB, GFLOP). Host-independent: A column.
STAGES = [
    ("attn_proj_qkvo", 2.862, 0.881, 1465.3),
    ("routed_experts", 17.666, 1.799, 1005.0),
    ("attn_core", 0.000, 0.713, 161.4),
    ("shared_expert", 0.069, 0.225, 125.6),
    ("dense_mlp_layer0", 0.101, 0.029, 51.5),
    ("router", 0.041, 0.092, 20.9),
    ("lm_head", 0.411, 0.000, 0.4),
    ("norm_rope", 0.000, 0.965, 0.0),
    ("moe_tail", 0.000, 0.818, 0.0),
    ("embedding", 0.002, 0.002, 0.0),
]

MMA_PEAK_TFLOPS = 60.0          # research/prefill_ridge.py:26
ZERO_ROW_FRACTION = 0.2026      # research/prefill-512-route-histogram.txt
DIVISORS = [485.0, 500.0, 530.0, 546.2, 610.0]


def rows(bw_gbs, tflops, discount):
    out = []
    for name, w, a, gflop in STAGES:
        if name == "routed_experts" and discount:
            w *= 1.0 - ZERO_ROW_FRACTION
        dram = (w + a) / bw_gbs * 1e3
        mma = gflop / tflops / 1e3 * 1e3
        out.append((name, w + a, gflop, dram, mma, max(dram, mma)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s-measured-ms", type=float, default=97.95,
                    help="M5 frontier 512-token prefill forward, ms")
    ap.add_argument("--score-pct-per-ms", type=float, default=0.371,
                    help="score %% per ms of prefill S")
    ap.add_argument("--tflops", type=float, default=MMA_PEAK_TFLOPS)
    args = ap.parse_args()

    for discount in (False, True):
        tag = ("routed weight bytes discounted "
               f"{ZERO_ROW_FRACTION:.2%} for zero-row experts" if discount
               else "no zero-row discount")
        print(f"\n=== M5 family floors, {tag} ===")
        base = rows(610.0, args.tflops, discount)
        print(f"{'stage':<18} {'GB':>7} {'GFLOP':>8} "
              + "".join(f"{f'dram@{d:g}':>11}" for d in DIVISORS)
              + f"{'mma@60':>9} {'bound':>7}")
        for i, (name, gb, gflop, _, mma, _) in enumerate(base):
            dr = [(gb / d * 1e3) for d in DIVISORS]
            bound = "compute" if mma > max(dr) else (
                "band" if mma > min(dr) else "memory")
            print(f"{name:<18} {gb:7.3f} {gflop:8.1f} "
                  + "".join(f"{v:11.2f}" for v in dr)
                  + f"{mma:9.2f} {bound:>7}")

        print(f"\n{'divisor GB/s':>13} {'sum max floor ms':>17} "
              f"{'UNATTRIBUTED ms':>16} {'% of S':>8} {'% of score':>11}")
        for d in DIVISORS:
            r = rows(d, args.tflops, discount)
            floor = sum(x[5] for x in r)
            un = args.s_measured_ms - floor
            print(f"{d:13.1f} {floor:17.2f} {un:16.2f} "
                  f"{un / args.s_measured_ms * 100:7.1f}% "
                  f"{un * args.score_pct_per_ms:10.2f}%")

        gb = sum(x[1] for x in base)
        gf = sum(x[2] for x in base)
        print(f"\n  whole-forward DRAM floor  "
              + "  ".join(f"{gb / d * 1e3:.2f}ms@{d:g}" for d in DIVISORS))
        print(f"  whole-forward MMA floor   "
              f"{gf / args.tflops / 1e3 * 1e3:.2f}ms@{args.tflops:g}TFLOP/s")
        print(f"  total A-column bytes      {gb:.3f} GB, "
              f"{gf:.1f} GFLOP, intensity {gf * 1e9 / (gb * 1e9):.1f} FLOP/B")


if __name__ == "__main__":
    main()
