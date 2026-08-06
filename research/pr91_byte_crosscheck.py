#!/usr/bin/env python3
"""Cross-check the A-column derived byte budget against the M-column profiler
bound-byte counter, family by family.

A column (algorithmic, transfers between hosts): bytes derived from
LagunaConstants geometry + observed shapes by research/prefill_budget.py.
M column (machine-determined, this host only): input bytes bound per command
buffer by the local-only GPUPROF hook, summed per family by
research/pr91_census.py.

The counter has two opposite biases, so agreement is not evidence of accuracy:
  - it de-duplicates repeated bindings inside one command buffer and ignores
    outputs entirely, which under-counts;
  - it charges every bound array in full whether or not the kernel reads all
    of it, which over-counts (the lm_head pruner stages are the extreme case).
The ratio column is therefore a consistency signal with a stated direction of
bias, not a calibration.
"""

# research/pr91-logs/step2-budget-m4.log (A column, GB, weight + activation)
DERIVED = {
    "attn_proj_qkvo": (2.862, 0.881),
    "routed_experts": (17.666, 1.799),
    "attn_core": (0.000, 0.713),
    "shared_expert": (0.069, 0.225),
    "dense_mlp_layer0": (0.101, 0.029),
    "router": (0.041, 0.092),
    "lm_head": (0.411, 0.000),
    "norm_rope": (0.000, 0.965),
    "moe_tail": (0.000, 0.818),
    "embedding": (0.002, 0.002),
}

# research/pr91-logs/step2-census-split1.log (M column, GB/forward)
PROFILED = {
    "routed_gather_gemm": 18.968,
    "steel_gemm_bf16": 4.552,
    "sort_scatter": 1.135,
    "attention_core": 0.696,
    "nvfp4_dense_qmm": 0.652,
    "elementwise": 1.633,
    "qk_norm_rope": 0.768,
    "moe_tail": 0.878,
    "rms_norm": 0.496,
    "router": 0.012,
    "lm_head": 0.959,
    "other": 0.211,
}

# Which profiler families carry which derived stages. steel_gemm_bf16 carries
# the BF16 attention projections *and* the router and layer-0 dense GEMMs,
# because all three land on the same steel kernels (see PR91 doc S2.2).
MAP = [
    ("routed_experts", ["routed_gather_gemm"]),
    ("attn_proj_qkvo + router + dense_mlp_layer0", ["steel_gemm_bf16"]),
    ("attn_core", ["attention_core"]),
    ("shared_expert", ["nvfp4_dense_qmm"]),
    ("lm_head", ["lm_head"]),
    ("norm_rope", ["qk_norm_rope", "rms_norm"]),
    ("moe_tail", ["moe_tail"]),
]
UNMAPPED_M = ["sort_scatter", "elementwise", "other"]
UNMAPPED_A = ["embedding"]


def derived(name):
    return sum(sum(DERIVED[s]) for s in name.split(" + "))


def main():
    print(f"{'derived stage(s)':<40} {'A GB':>7} {'M GB':>7} {'M/A':>6}")
    a_tot = m_tot = 0.0
    for stages, fams in MAP:
        a = derived(stages)
        m = sum(PROFILED[f] for f in fams)
        a_tot += a
        m_tot += m
        print(f"{stages:<40} {a:7.3f} {m:7.3f} {m / a:6.3f}")
    print(f"{'-' * 62}")
    print(f"{'mapped subtotal':<40} {a_tot:7.3f} {m_tot:7.3f} "
          f"{m_tot / a_tot:6.3f}")
    a_un = sum(sum(DERIVED[s]) for s in UNMAPPED_A)
    m_un = sum(PROFILED[f] for f in UNMAPPED_M)
    print(f"{'unmapped (' + ','.join(UNMAPPED_M) + ')':<40} "
          f"{a_un:7.3f} {m_un:7.3f}")
    print(f"{'TOTAL':<40} {a_tot + a_un:7.3f} {m_tot + m_un:7.3f} "
          f"{(m_tot + m_un) / (a_tot + a_un):6.3f}")
    print("\nnote: A has no counterpart for the sort/scatter, elementwise and "
          "'other' families;\n      prefill_budget.py folds their traffic into "
          "the norm_rope and moe_tail\n      activation rows, so the unmapped "
          f"{m_un:.3f} GB of M is the residual the A column\n      does not "
          "itemise.")


if __name__ == "__main__":
    main()
