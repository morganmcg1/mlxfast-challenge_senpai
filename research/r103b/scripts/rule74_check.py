#!/usr/bin/env python3
"""Rule-74 rider: do f720e9e7's four comment-stripped Vendor files change any
JIT-emitted MSL text between OLD (comments present) and NEW (comments deleted)?"""
import re
import sys
import collections

root = sys.argv[1]


def load(p):
    d = {}
    for line in open(p):
        h, _, n = line.rstrip("\n").partition("\t")
        if n:
            d[n] = h
    return d


old = load(f"{root}/research/r103b/artifacts/msl_sha256_old.tsv")
new = load(f"{root}/research/r103b/artifacts/msl_sha256_new.tsv")

fam = [
    ("quantized.cpp + jit_kernels.cpp (nvfp4 / affine quant)", r"^(nvfp4_|affine_quantize)"),
    ("matmul.cpp + jit_kernels.cpp (steel gemm / gemv)", r"^(steel_gemm|gemv_)"),
    ("jit_kernels.cpp (steel attention)", r"^steel_attention"),
    ("sdpa_vector.h (JIT sdpa)", r"sdpa_vector"),
]

# which JIT libraries are actually dispatched, and in which segment
MARK = "custom_kernel_laguna_decode_embedding_rope_atlas"


def dispatch_segments(p):
    rows = []
    for line in open(p):
        f = line.rstrip("\n").split("\t")
        if len(f) >= 2:
            rows.append(f[1])
    marks = [i for i, k in enumerate(rows) if k.startswith(MARK)]
    prefill = rows[: marks[0]] if marks else rows
    decode = rows[marks[0]:] if marks else []
    return rows, prefill, decode


all_o, pre_o, dec_o = dispatch_segments("/tmp/r103b/dump/old/dispatch.tsv")
cnt_pre = collections.Counter(pre_o)
cnt_dec = collections.Counter(dec_o)

print(f"OLD dispatch rows: total={len(all_o)} prefill={len(pre_o)} decode={len(dec_o)}\n")

for label, pat in fam:
    names = sorted(n for n in set(old) | set(new) if re.search(pat, n))
    diff = [n for n in names if n in old and n in new and old[n] != new[n]]
    only = [n for n in names if (n in old) != (n in new)]
    print(f"## {label}")
    print(f"   libraries in corpus: {len(names)}   differing OLD vs NEW: {len(diff)}   only-one-side: {len(only)}")
    for n in names:
        print(f"     {'SAME' if old.get(n) == new.get(n) else 'DIFF'}  prefill_dispatch={cnt_pre.get(n, 0):5d}  decode_dispatch={cnt_dec.get(n, 0):5d}  {n}")
    if not names:
        print("     (none -- not JIT-compiled in this run)")
    print()

print("=== per-decode-step presence (OLD) of the rule-74 JIT families ===")
marks = [i for i, k in enumerate(all_o) if k.startswith(MARK)]
bounds = marks + [len(all_o)]
watch = [n for _, pat in fam for n in sorted(set(old) | set(new)) if re.search(pat, n)]
for s in range(len(marks)):
    seg = all_o[bounds[s]:bounds[s + 1]]
    c = collections.Counter(seg)
    hits = {n.split("_bfloat16")[0]: c[n] for n in watch if c[n]}
    print(f"  decode step {s}: rows={len(seg):5d}  rule74-family dispatches={sum(hits.values()):4d}  {hits}")
