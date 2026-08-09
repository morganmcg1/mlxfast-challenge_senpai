#!/usr/bin/env python3
"""r99-D Part 1: common-mode-normalised decode census delta, old base vs new frontier.

Old column: research/maple-frieren-r94-decode-residue-ledger.md, base
d549d3185695 (values originate in research/maple-nezuko-r92-barrier-hoist-
generalization.md:70-100).  SPLIT=1, M4 Pro 20-core, same instrument family.
That base is *pre*-r96-a, so its ring is the 2-deep loop; see §4.2 of the note
for why this matters for causal attribution.
New column: research/r99d-logs/r99d-split1.{2,3}.log (base c6c66344, unmodified
submitted surface, this session).

Rig/thermal/session drift is absorbed by a robust common mode: the median of the
per-kernel new/old ratio over kernels with old >= 50 us/step.  Scale is the
normalised MAD of that same set.  Excess is what a kernel does beyond common mode.
"""
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# label -> us/step, SPLIT=1, base e510bb3d (r94 ledger table)
OLD = {
    "routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2": 1497.7,
    "decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1": 1340.1,
    "oproj_act_h64_v1_lm1_pw1_sc1_se1": 1117.7,
    "routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6": 858.9,
    "sliding_fused_attn_ring_v1": 636.0,
    "lmhead_int5_base_coarse_delta_bf16_v1": 420.3,
    "decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1": 362.8,
    # old label carried the _pf1 router-prefetch suffix; same dispatch site
    "residual_rms_router_bf16_2048_rpg8_keys_v1": 312.8,
    "oproj_act_h48_v1_lm1_pw1_sc1_se1": 301.8,
    "shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1": 287.1,
    "dense_gate_up_swiglu_bf16_v1": 269.4,
    "gate_sp_h64_v1": 248.0,
    "full_fused_attn_grow_v1": 229.7,
    "prefill_router_tournament_ordinal_norm_active64_v2": 185.5,
    "rmsbfloat16": 141.9,
    "dense_down_residual_bf16_v1": 133.8,
    "gate_sp_h48_v1": 80.2,
    "lmhead_exact_fused_int5_sparse_refine_v1": 77.0,
    "argmax_bfloat16": 9.0,
    "lmhead_exact_winner_bf16_midpoint_threshold_v1": 4.7,
    "lmhead_coarse_argmax_stage1_v5": 4.1,
    "decode_embedding_rope_atlas_bf16_2048_v2": 3.5,
    "gather_frontbfloat16_int32_int_2": 3.4,
    "residual_rms_bf16_2048_v1": 2.9,
}

ROW = re.compile(r"^\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)\s+([0-9.]+)\s+(\S+)\s*$")
STEADY = re.compile(
    r"per steady step: wall=([0-9.]+) ms gpu_busy_sum=([0-9.]+) ms "
    r"gpu_busy_union=([0-9.]+) ms gap=([0-9.]+) ms \(([0-9.]+)% of wall\) "
    r"cbs=([0-9.]+) dispatches=([0-9.]+)"
)


def parse(path):
    rows, steady = {}, None
    for line in Path(path).read_text().splitlines():
        m = STEADY.search(line)
        if m:
            steady = tuple(float(x) for x in m.groups())
            continue
        m = ROW.match(line)
        if m and "|" not in m.group(5):
            rows[m.group(5)] = (float(m.group(1)), float(m.group(3)), float(m.group(4)))
    return rows, steady


def main():
    reps = [parse(ROOT / "r99d-logs" / f"r99d-split1.{i}.log") for i in (2, 3)]
    labels = set(reps[0][0]) & set(reps[1][0])
    new = {k: statistics.mean(r[0][k][0] for r in reps) for k in labels}
    calls = {k: reps[0][0][k][1] for k in labels}

    missing = set(OLD) ^ set(new)
    if missing:
        print(f"label set mismatch: {sorted(missing)}", file=sys.stderr)
        return 1

    ref = [new[k] / OLD[k] for k in OLD if OLD[k] >= 50.0]
    cm = statistics.median(ref)
    mad = statistics.median(abs(r - cm) for r in ref)
    sigma = 1.4826 * mad

    print(f"reference set n={len(ref)}  common mode x{cm:.5f}  robust sigma {sigma * 100:.3f}%")
    for i, (_, steady) in enumerate(reps, start=2):
        print(
            f"  rep{i}: wall={steady[0]:.3f} busy={steady[1]:.3f} gap={steady[3]:.3f} "
            f"cbs={steady[5]:.0f} dispatches={steady[6]:.0f}"
        )
    print()
    print(f"{'kernel':<52}{'calls':>6}{'old':>9}{'new':>9}{'ratio':>9}{'excess':>9}{'exc%':>8}{'z':>8}")
    tot_old = tot_new = tot_exc = 0.0
    for k in sorted(OLD, key=lambda k: -OLD[k]):
        o, n = OLD[k], new[k]
        exc = n - o * cm
        z = (n / o - cm) / (sigma * n / o) if o > 0 else float("nan")
        tot_old += o
        tot_new += n
        tot_exc += exc
        print(
            f"{k:<52}{calls[k]:>6.0f}{o:>9.1f}{n:>9.1f}{n / o:>9.5f}"
            f"{exc:>9.2f}{100 * exc / o:>8.2f}{z:>8.1f}"
        )
    print(
        f"{'TOTAL':<52}{406:>6}{tot_old:>9.1f}{tot_new:>9.1f}{tot_new / tot_old:>9.5f}"
        f"{tot_exc:>9.2f}{100 * tot_exc / tot_old:>8.2f}"
    )
    print(f"\nraw delta {tot_new - tot_old:+.1f} us/step = common mode {tot_old * (cm - 1):+.1f} + excess {tot_exc:+.1f}")

    # score translation: M4 excess -> fraction of M4 decode step -> M5 step -> score %
    m4_wall = 8223.0  # us/step, SPLIT=0 rep2 (SPLIT=1 wall is instrument-inflated)
    m5_step = 4893.7  # us/step, pinned baseline decode
    pct_per_us = 0.015280  # score % per us/step of M5 decode
    print(f"\nscore translation (M4 wall {m4_wall:.0f} us -> M5 {m5_step:.1f} us, {pct_per_us} %/us)")
    for k in ("sliding_fused_attn_ring_v1", "residual_rms_router_bf16_2048_rpg8_keys_v1",
              "full_fused_attn_grow_v1"):
        exc = new[k] - OLD[k] * cm
        print(f"  {k:<52}{exc / m4_wall * m5_step * pct_per_us:>8.4f} % of score")
    print(f"  {'ALL excess':<52}{tot_exc / m4_wall * m5_step * pct_per_us:>8.4f} % of score")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
