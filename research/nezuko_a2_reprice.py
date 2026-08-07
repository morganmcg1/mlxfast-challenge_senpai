#!/usr/bin/env python3
"""Re-price the PR #158 §2.b decode census with a measured per-CB cost and
per-kernel exposure factors.

PR #158 published

    exposed_i = n_i * (raw_split1_us_per_call_i - 1.419)

where 1.419 us/dispatch was the SPLIT=1 de-inflation implied by a per-command
-buffer cost c = 1.596 us.  A0's serial-arm regression gives c = 0.540 us/CB, so
the de-inflation is 0.540 * (1 - 45/406) = 0.480 us/dispatch and the isolated
("zero-overlap") work per call is

    work_i = n_i * (published_us_per_call_i + 1.419 - 0.480)

The isolated column is still not the marginal price of the kernel on the step,
because concurrent encoding hides part of it.  The marginal price is

    effective_i = work_i * E_i

with E_i the measured exposure factor (1 = fully exposed, 0 = fully shadowed).
E defaults to the step-wide mean when a kernel has no direct measurement.

Usage:
    nezuko_a2_reprice.py [--exposure exposure.json] [--top 20]
"""
from __future__ import annotations

import argparse
import json
import sys

# (published exposed us/step, n/step, published us/call, kernel)
CENSUS_2B = [
    (1445.4, 39, 37.06, "routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"),
    (1291.5, 30, 43.05, "decode_nvfp4_qkv_h64"),
    (1074.0, 30, 35.80, "oproj_act_h64"),
    (812.8, 39, 20.84, "routed_shared_nvfp4_down_residual_bf16_r1_v5"),
    (592.2, 30, 19.74, "sliding_fused_attn_ring_v1"),
    (420.4, 1, 420.44, "lmhead_int5_base_coarse_delta"),
    (349.8, 10, 34.98, "decode_nvfp4_qkv_h48"),
    (288.9, 10, 28.89, "oproj_act_h48"),
    (268.6, 1, 268.59, "dense_gate_up_swiglu"),
    (264.5, 39, 6.78, "residual_rms_router_rpg8_keys_v1"),
    (239.9, 10, 23.99, "full_fused_attn_grow_v1"),
    (237.6, 39, 6.09, "shared_nvfp4_swiglu_qmv_rows1"),
    (199.2, 30, 6.64, "gate_sp_h64"),
    (146.7, 39, 3.76, "decode_router_top8_ordinal_table_norm"),
    (133.6, 1, 133.59, "dense_down_residual"),
    (84.5, 41, 2.06, "rmsbfloat16"),
    (74.3, 1, 74.31, "lmhead_exact_fused_int5_sparse_refine"),
    (63.1, 10, 6.31, "gate_sp_h48"),
    (19.5, 6, 3.25, "six kernels below 8 us/step"),
]

C_PR158 = 1.596          # us/CB, PR #158 §4.5
DEINFLATE_PR158 = 1.419  # us/dispatch, PR #158 §2.a
C_A0 = 0.540             # us/CB, this PR, A0 serial-arm regression
CBS_SHIP = 45.0
DISPATCHES = 406.0
BUSY_SHIP = 7999.4       # us/step, SPLIT=0 concurrent
SCORE_PER_US = 0.01464   # % score per us/step removed from decode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exposure", help="JSON map kernel -> E, literal or @file")
    ap.add_argument("--c", type=float, default=C_A0,
                    help="measured per-command-buffer cost, us/CB")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    c = args.c
    exposure = {}
    if args.exposure:
        if args.exposure.startswith("@"):
            exposure = json.load(open(args.exposure[1:]))
        else:
            exposure = json.loads(args.exposure)

    deinflate_a0 = c * (1 - CBS_SHIP / DISPATCHES)
    correction = DEINFLATE_PR158 - deinflate_a0

    work = []
    for exposed, n, us_call, name in CENSUS_2B:
        w = n * (us_call + correction)
        work.append((w, n, name, exposed))
    total_work = sum(w for w, _, _, _ in work)

    overlap = total_work + CBS_SHIP * c - BUSY_SHIP

    # Kernels named in the exposure map keep their measured E. The remaining
    # work absorbs whatever overlap those kernels do not account for, so E_rest
    # is a real closure test: if the named hiders explain the whole 448 us,
    # E_rest lands on 1.0 rather than being forced there.
    listed_eff = sum(w * exposure[name] for w, _, name, _ in work
                     if name in exposure)
    rest_work = sum(w for w, _, name, _ in work if name not in exposure)
    E_rest = ((BUSY_SHIP - CBS_SHIP * c - listed_eff) / rest_work
              if rest_work else float("nan"))

    rows = []
    for w, n, name, exposed in work:
        E = exposure.get(name, E_rest)
        rows.append((w * E, w, E, n, name, exposed))

    old_rank = {name: i for i, (_, _, _, _, name, _) in
                enumerate(sorted(rows, key=lambda r: -r[5]), 1)}
    rows.sort(key=lambda r: -r[0])

    print(f"per-CB cost:        PR158 {C_PR158:.3f} -> A0 {c:.3f} us/CB "
          f"({C_PR158 / c:.1f}x)")
    print(f"de-inflation:       PR158 {DEINFLATE_PR158:.3f} -> A0 "
          f"{deinflate_a0:.3f} us/dispatch (correction {correction:+.3f})")
    print(f"isolated work sum:  {total_work:.1f} us/step "
          f"(PR158 census total {sum(r[5] for r in rows):.1f})")
    print(f"implied overlap:    {overlap:.1f} us/step "
          f"(A0 measured 448 +- 31)")
    print(f"closure test:       named hiders absorb {total_work - listed_eff - rest_work:.1f} "
          f"us -> E_rest = {E_rest:.3f} (1.000 == fully explained)")
    print(f"identity check:     work*E + 45c = "
          f"{sum(r[0] for r in rows) + CBS_SHIP * c:.1f} vs busy "
          f"{BUSY_SHIP:.1f} us/step\n")

    hdr = (f"  {'rank':>4} {'d':>4} {'effective':>10} {'isolated':>9} "
           f"{'E':>6} {'n':>4} {'PR158':>9} {'score%':>8}  kernel")
    print(hdr)
    for i, (eff, w, E, n, name, exposed) in enumerate(rows[:args.top], 1):
        drank = old_rank[name] - i
        print(f"  {i:4d} {drank:+4d} {eff:10.1f} {w:9.1f} {E:6.3f} {n:4d} "
              f"{exposed:9.1f} {eff * SCORE_PER_US:8.2f}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
