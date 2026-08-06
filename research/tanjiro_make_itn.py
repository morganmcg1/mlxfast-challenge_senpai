#!/usr/bin/env python3
"""Cost-decomposition probes for the sliding fused-attention kernel.

Each probe truncates the main row loop to 1, 2 or 4 of its 8 iterations by
lowering the loop bound. Regressing dispatch time on iteration count separates
the fixed prologue/epilogue cost from the per-iteration cost, which bounds what
any prologue-side optimisation (pre-barrier prefetch) can possibly buy.

The probes compute wrong attention on purpose; they are diagnostics, never
candidates.
"""
import pathlib

SRC = pathlib.Path(
    "research/tanjiro_kernels/laguna_sliding_fused_attn_ring_v1.metal")
OLD = "for (; i + BN < N; i += 2 * BN) {"

text = SRC.read_text()
assert text.count(OLD) == 1

for iterations, bound in ((1, 64), (2, 128), (4, 256)):
    name = f"laguna_sliding_fused_attn_ring_v1_it{iterations}"
    out = text.replace(OLD, f"for (; i + BN < {bound}; i += 2 * BN) {{")
    out = out.replace("custom_kernel_laguna_sliding_fused_attn_ring_v1(",
                      f"custom_kernel_{name}(")
    path = pathlib.Path(f"research/tanjiro_kernels/{name}.metal")
    path.write_text(out)
    print(f"wrote {path}")
