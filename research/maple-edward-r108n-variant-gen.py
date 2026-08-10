#!/usr/bin/env python3
"""R108-N stage 1: emit probe-only variants of laguna_sliding_fused_attn_ring_v1.

The variants are timing probes for fern_r100_attn_probe.swift only.  They are
written to a scratch path and never touch the scored surface, so the stage-1
numstat contract stays empty.  Correctness of each mechanism is argued
separately in the report; the probe measures issue cost, not tokens.

  m1  factor == 1.0 fast path on the accumulator rescale.  Whenever the running
      max is unchanged the base multiplies the accumulator by exactly 1.0, so
      the fast path drops one multiply per (dim, head, row).
  m3  epilogue: one reciprocal per head instead of four divides.

usage: maple-edward-r108n-variant-gen.py SRC OUT m1[,m3]
"""
import re
import sys

src_path, out_path, spec = sys.argv[1], sys.argv[2], sys.argv[3]
variants = set(spec.split(","))
lines = open(src_path).read().split("\n")

STAGES = [("pair", "pipe_va"), ("pipeb", "pipe_vb"),
          ("pipec", "pipe_vc"), ("piped", "pipe_vd")]

if "m1" in variants:
    for stage, vprefix in STAGES:
        blocks = {0: [], 1: []}
        idx = {0: [], 1: []}
        pat = re.compile(
            r"^(\s*)(pair_(?:sum|o)([01])(?:\[(\d)\])?) = \2 \* "
            + stage + r"_factor\3 \+ (.+);$")
        for i, ln in enumerate(lines):
            m = pat.match(ln)
            if m:
                h = int(m.group(3))
                blocks[h].append((m.group(1), m.group(2), m.group(5)))
                idx[h].append(i)
        assert len(blocks[0]) == 5 and len(blocks[1]) == 5, (
            stage, len(blocks[0]), len(blocks[1]))
        last = max(idx[0] + idx[1])
        indent = blocks[0][0][0]
        new = []
        for h in (0, 1):
            f = f"{stage}_factor{h}"
            new.append(f"{indent}if ({f} == U(1.0f)) {{")
            for ind, lhs, rest in blocks[h]:
                new.append(f"{indent}    {lhs} = {lhs} + {rest};")
            new.append(f"{indent}}} else {{")
            for ind, lhs, rest in blocks[h]:
                new.append(f"{indent}    {lhs} = {lhs} * {f} + {rest};")
            new.append(f"{indent}}}")
        drop = set(idx[0] + idx[1])
        lines = ([ln for i, ln in enumerate(lines) if i <= last and i not in drop]
                 + new
                 + [ln for i, ln in enumerate(lines) if i > last])

if "m3" in variants:
    out = []
    for ln in lines:
        m = re.match(
            r"^(\s*)pair_o([01])\[(\d)\] = pair_sum\2 == 0 \? acc\2(\d) : "
            r"\(acc\2\4 / pair_sum\2\);$", ln)
        if m:
            ind, h, d, a = m.group(1), m.group(2), m.group(3), m.group(4)
            if d == "0":
                out.append(f"{ind}const U pair_inv{h} = "
                           f"pair_sum{h} == 0 ? U(1.0f) : U(1.0f) / pair_sum{h};")
            out.append(f"{ind}pair_o{h}[{d}] = acc{h}{a} * pair_inv{h};")
        else:
            out.append(ln)
    assert sum(1 for l in out if "pair_inv" in l) == 10, "m3 rewrite miscount"
    lines = out

open(out_path, "w").write("\n".join(lines))
print(f"variants={sorted(variants)} out={out_path} lines={len(lines)}")
