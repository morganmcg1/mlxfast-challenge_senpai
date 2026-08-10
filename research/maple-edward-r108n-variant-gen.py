#!/usr/bin/env python3
"""R108-N stage 1: emit probe-only variants of laguna_sliding_fused_attn_ring_v1.

The variants are timing probes for fern_r100_attn_probe.swift only.  They are
written to a scratch path and never touch the scored surface, so the stage-1
numstat contract stays empty.  Correctness of each mechanism is argued
separately in the report; the probe measures issue cost, not tokens.

  m1  factor == 1.0 fast path on the accumulator rescale.  Whenever the running
      max is unchanged the base multiplies the accumulator by exactly 1.0, so
      the fast path drops one multiply per (dim, head, row).
  m2  upper bound on the ring-substitution predicate peel: the substitute
      argument is forced false, so the compiler drops the four per-iteration
      compares and the threadgroup path.  A correct peel keeps a single
      post-loop fix-up, so the real gain is smaller than this arm.
  m3  epilogue: one reciprocal per head instead of four divides.

usage: maple-edward-r108n-variant-gen.py SRC OUT m1[,m2,m3]
"""
import re
import sys

src_path, out_path, spec = sys.argv[1], sys.argv[2], sys.argv[3]
variants = set(spec.split(","))
lines = open(src_path).read().split("\n")

STAGES = [("pair", "pipe_va"), ("pipeb", "pipe_vb"),
          ("pipec", "pipe_vc"), ("piped", "pipe_vd")]

KERNEL = "laguna_sliding_fused_attn_ring_v1"


def region(lines):
    """Line index bounds of the sliding kernel's Metal source string.

    The full-attention twin later in the file repeats the same statement text
    twice, so an unscoped rewrite would edit three kernels at once.
    """
    k = next(i for i, l in enumerate(lines) if KERNEL in l)
    lo = next(i for i in range(k, len(lines)) if lines[i].strip() == 'source: """')
    hi = next(i for i in range(lo + 1, len(lines)) if lines[i].startswith('"""'))
    return lo, hi


if "m1" in variants:
    for stage, vprefix in STAGES:
        lo, hi = region(lines)
        blocks = {0: [], 1: []}
        idx = {0: [], 1: []}
        pat = re.compile(
            r"^(\s*)(pair_(?:sum|o)([01])(?:\[(\d)\])?) = \2 \* "
            + stage + r"_factor\3 \+ (.+);$")
        for i in range(lo, hi):
            m = pat.match(lines[i])
            if m:
                ln = lines[i]
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

if "m2" in variants:
    lo, hi = region(lines)
    n = 0
    for i in range(lo, hi):
        if "T_LOAD_K(" in lines[i] or "T_LOAD_V(" in lines[i]:
            lines[i], c = re.subn(r"\bsub_[a-d]\b", "false", lines[i])
            n += c
    assert n == 8, f"m2 predicate count {n}"

if "m3" in variants:
    lo, hi = region(lines)
    out = []
    for i, ln in enumerate(lines):
        m = re.match(
            r"^(\s*)pair_o([01])\[(\d)\] = pair_sum\2 == 0 \? acc\2(\d) : "
            r"\(acc\2\4 / pair_sum\2\);$", ln) if lo <= i < hi else None
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
