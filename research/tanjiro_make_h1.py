#!/usr/bin/env python3
"""Derive the R1 "one query head per threadgroup" sliding-attention variant.

R0 maps one threadgroup to a *pair* of query heads that share a KV head, so
32 threadgroups cover 64 heads and threadgroup memory is 18432 B. R1 maps one
threadgroup to one head (64 threadgroups, 9472 B). The whole lane-1 half of
the kernel disappears, so the transform is: a handful of explicit prologue
rewrites plus a statement-level filter that drops every statement mentioning a
lane-1 identifier.

Statement splitting is brace/paren aware, which the equivalent line filter is
not: several lane-1 statements in the epilogue span four physical lines and
only the first and last mention a banned name.
"""
import pathlib
import re

SRC = pathlib.Path(
    "research/tanjiro_kernels/laguna_sliding_fused_attn_ring_v1.metal")
DST = pathlib.Path(
    "research/tanjiro_kernels/laguna_sliding_fused_attn_ring_v1_h1.metal")

BANNED = {
    "acc1", "head1", "pair_exp1", "pair_factor1", "pair_global_factor1",
    "pair_global_max1", "pair_max1", "pair_new_max1", "pair_o1", "pair_out1",
    "pair_q1", "pair_score1", "pair_sum1", "pipeb_exp1", "pipeb_factor1",
    "pipeb_new_max1", "pipeb_score1", "tg_q1",
}

REWRITES = [
    ("custom_kernel_laguna_sliding_fused_attn_ring_v1(",
     "custom_kernel_laguna_sliding_fused_attn_ring_v1_h1("),
    ("uint pair_tg = threadgroup_position_in_grid.x;\n"
     "uint head0 = pair_tg * 2;\n",
     "uint head0 = threadgroup_position_in_grid.x;\n"),
    ("if (sg < 3) {", "if (sg < 2) {"),
    ("""        sg == 0 ? raw_queries + head0 * head_dim
        : sg == 1 ? raw_queries + head1 * head_dim
                  : raw_keys + kv_head * head_dim;""",
     """        sg == 0 ? raw_queries + head0 * head_dim
                : raw_keys + kv_head * head_dim;"""),
    ("        sg == 2 ? key_weight : query_weight;",
     "        sg == 1 ? key_weight : query_weight;"),
    ("        sg == 0 ? tg_q0 : sg == 1 ? tg_q1 : tg_k;",
     "        sg == 0 ? tg_q0 : tg_k;"),
    ("} else if (sg == 3) {", "} else if (sg == 2) {"),
    ("threadgroup U outputs[4 * BN * BDP];",
     "threadgroup U outputs[2 * BN * BDP];"),
    ("threadgroup U max_scores[2 * BN];", "threadgroup U max_scores[BN];"),
    ("threadgroup U sum_exp_scores[2 * BN];",
     "threadgroup U sum_exp_scores[BN];"),
]


def chunks(src):
    """Split into statements and brace tokens, ignoring nested (), [] depth."""
    out, cur, depth = [], "", 0
    for c in src:
        cur += c
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and c in ";{}":
            out.append(cur)
            cur = ""
    if cur.strip():
        out.append(cur)
    return out


def main():
    text = SRC.read_text()
    head, sep, body = text.partition(
        "[[kernel]] void custom_kernel_laguna_sliding_fused_attn_ring_v1(")
    assert sep, "entry point not found"
    body = sep + body
    for old, new in REWRITES:
        assert old in body, f"anchor missing: {old[:60]!r}"
        body = body.replace(old, new, 1)
    kept, dropped = [], 0
    for chunk in chunks(body):
        names = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", chunk))
        if names & BANNED:
            dropped += 1
            continue
        kept.append(chunk)
    result = head + "".join(kept)
    leftover = sorted(n for n in BANNED
                      if re.search(rf"\b{n}\b", result))
    assert not leftover, f"lane-1 names survived: {leftover}"
    DST.write_text(result)
    print(f"wrote {DST} ({len(result)} bytes, dropped {dropped} statements)")


main()
