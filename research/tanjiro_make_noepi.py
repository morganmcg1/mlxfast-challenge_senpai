#!/usr/bin/env python3
"""Emit a diagnostic sliding-attention variant with the cross-simdgroup epilogue
replaced by a trivial store.

The real epilogue transposes 8 output planes through a 4-plane threadgroup
buffer, which costs 3 threadgroup barriers, 2 simd_max and 12 simd_sum. This
variant keeps the prologue and the full main loop but writes the per-simdgroup
partials directly, so `R0 - noepi` isolates the epilogue's cost.

The output is numerically WRONG by construction. It is a cost probe only and is
never a submission candidate.
"""
import pathlib
import re

KDIR = pathlib.Path(__file__).resolve().parent / "tanjiro_kernels"
SRC = KDIR / "laguna_sliding_fused_attn_ring_v1.metal"
DST = KDIR / "laguna_sliding_fused_attn_ring_v1_noepi.metal"

EPILOGUE_START = "constexpr int pair_planes = 2;"

# Keeps every value the main loop produced live so the loop cannot be dead-coded,
# and keeps the threadgroup arrays referenced so the tgmem footprint is unchanged.
REPLACEMENT = """constexpr int pair_planes = 2;
if (lane == 0) {
    max_scores[sg] = pair_max0;
    max_scores[BN + sg] = pair_max1;
    sum_exp_scores[sg] = pair_sum0;
    sum_exp_scores[BN + sg] = pair_sum1;
}
outputs[lane * BDP + sg] = pair_o0[0] + pair_o0[1] + pair_o0[2] + pair_o0[3];
if (lane == 0) {
    device bfloat* pair_out0 =
        attended + head0 * head_dim + sg * v_per_thread;
    device bfloat* pair_out1 =
        attended + head1 * head_dim + sg * v_per_thread;
    for (int p = 0; p < v_per_thread; ++p) {
        pair_out0[p] = static_cast<bfloat>(pair_o0[p] + max_scores[sg]);
        pair_out1[p] = static_cast<bfloat>(pair_o1[p] + sum_exp_scores[sg]);
    }
}
}
"""


def main() -> int:
    text = SRC.read_text()
    idx = text.index(EPILOGUE_START)
    head, tail = text[:idx], text[idx:]
    # The kernel body ends with the entry-point brace; keep whatever follows it.
    close = tail.rindex("}\n")
    trailing = tail[close + 2:]
    out = head + REPLACEMENT + trailing
    out = re.sub(r"custom_kernel_laguna_sliding_fused_attn_ring_v1\b",
                 "custom_kernel_laguna_sliding_fused_attn_ring_v1_noepi", out)
    DST.write_text(out)
    print(f"wrote {DST} ({len(out)} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
