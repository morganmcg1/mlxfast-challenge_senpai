#!/usr/bin/env python3
"""Generate sliding fused-attention kernel variants from the extracted R0 text.

Research-only. The variants are compiled and timed by
`research/tanjiro_occupancy_audit.swift bench`, which also runs a kernel-level
bitwise oracle against R0, so a variant that changes any rounding is caught
before it reaches `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

R2 deepens the software pipeline from 2 key/value slots per loop iteration to
`slots`. Each simdgroup still visits rows sg, sg+32, sg+64, ... in exactly the
same order and folds them into the online softmax in exactly the same order, so
the result is bitwise identical by construction; only the number of loads in
flight changes.
"""

import re
import sys
from pathlib import Path

KERNELS = Path("research/tanjiro_kernels")
R0 = KERNELS / "laguna_sliding_fused_attn_ring_v1.metal"

LOOP_START = "int i = sg;\nfor (; i + BN < N; i += 2 * BN) {"
LOOP_END = "    pair_keys += 2 * inner_k_stride;\n    pair_values += 2 * inner_v_stride;\n}"


def slot_body(tag: str) -> str:
    """One online-softmax fold, identical in shape to R0's slot-a body."""
    lines = [f"    U {tag}_score0 = 0;", f"    U {tag}_score1 = 0;"]
    for j in range(4):
        lines.append(f"    {tag}_score0 += pair_q0[{j}] * pipe_k{tag}[{j}];")
        lines.append(f"    {tag}_score1 += pair_q1[{j}] * pipe_k{tag}[{j}];")
    lines += [
        f"    {tag}_score0 = simd_sum({tag}_score0);",
        f"    {tag}_score1 = simd_sum({tag}_score1);",
        "",
        f"    U {tag}_new_max0 = metal::max(pair_max0, {tag}_score0);",
        f"    U {tag}_new_max1 = metal::max(pair_max1, {tag}_score1);",
        f"    U {tag}_factor0;",
        f"    U {tag}_factor1;",
        f"    LAGUNA_RESCALE({tag}_factor0, pair_max0 - {tag}_new_max0);",
        f"    LAGUNA_RESCALE({tag}_factor1, pair_max1 - {tag}_new_max1);",
        f"    U {tag}_exp0 = metal::fast::exp({tag}_score0 - {tag}_new_max0);",
        f"    U {tag}_exp1 = metal::fast::exp({tag}_score1 - {tag}_new_max1);",
        "",
        f"    pair_max0 = {tag}_new_max0;",
        f"    pair_max1 = {tag}_new_max1;",
        f"    pair_sum0 = pair_sum0 * {tag}_factor0 + {tag}_exp0;",
        f"    pair_sum1 = pair_sum1 * {tag}_factor1 + {tag}_exp1;",
        "",
    ]
    for p in range(4):
        lines.append(
            f"    pair_o0[{p}] = pair_o0[{p}] * {tag}_factor0"
            f" + {tag}_exp0 * pipe_v{tag}{p};")
        lines.append(
            f"    pair_o1[{p}] = pair_o1[{p}] * {tag}_factor1"
            f" + {tag}_exp1 * pipe_v{tag}{p};")
    return "\n".join(lines)


def pipelined_loop(slots: int) -> str:
    tags = [chr(ord("a") + s) for s in range(slots)]
    out = ["int i = sg;",
           f"for (; i + {slots - 1} * BN < N; i += {slots} * BN) {{"]
    for s, tag in enumerate(tags):
        off = "" if s == 0 else f" + {s} * inner_k_stride"
        out.append(f"    const device bfloat* pk_{tag} = pair_keys{off};")
    for s, tag in enumerate(tags):
        off = "" if s == 0 else f" + {s} * inner_v_stride"
        out.append(f"    const device bfloat* pv_{tag} = pair_values{off};")
    for s, tag in enumerate(tags):
        term = "uint(i)" if s == 0 else f"uint(i + {s} * BN)"
        out.append(f"    const bool sub_{tag} = {term} == widx;")
    for tag in tags:
        out.append(f"    U pipe_k{tag}[4];")
    for tag in tags:
        out.append(f"    bfloat pipe_v{tag}0, pipe_v{tag}1,"
                   f" pipe_v{tag}2, pipe_v{tag}3;")
    # Every load is issued before the first dependent use, so `slots` key and
    # value fetches are in flight across the serial softmax chain.
    for tag in tags:
        out.append(f"    T_LOAD_K(pipe_k{tag}, sub_{tag}, pk_{tag});")
    for tag in tags:
        out.append(f"    T_LOAD_V(pipe_v{tag}0, pipe_v{tag}1, pipe_v{tag}2,"
                   f" pipe_v{tag}3, sub_{tag}, pv_{tag});")
    out.append("")
    for tag in tags:
        out.append(slot_body(tag))
        out.append("")
    out.append(f"    pair_keys += {slots} * inner_k_stride;")
    out.append(f"    pair_values += {slots} * inner_v_stride;")
    out.append("}")
    return "\n".join(out)


def main() -> int:
    text = R0.read_text()
    start = text.index(LOOP_START)
    end = text.index(LOOP_END) + len(LOOP_END)
    for slots in (4, 8):
        name = f"laguna_sliding_fused_attn_ring_v1_p{slots}"
        variant = text[:start] + pipelined_loop(slots) + text[end:]
        variant = variant.replace(
            "custom_kernel_laguna_sliding_fused_attn_ring_v1(",
            f"custom_kernel_{name}(")
        assert f"custom_kernel_{name}(" in variant
        assert re.search(r"i \+= \d+ \* BN", variant)
        path = KERNELS / f"{name}.metal"
        path.write_text(variant)
        print(f"wrote {path} ({len(variant)} bytes, {slots} slots)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
