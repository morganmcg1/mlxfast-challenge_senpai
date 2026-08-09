#!/usr/bin/env python3
"""r92-b stage 3: localise the g17s excess inside the two attention kernels.

Each ablation edits the dumped MSL and is censused on both architectures. The
comparison is always g16s vs g17s *within one variant*, so every row stays a
matched null: identical source, identical flags, only -arch differs. Ablations
change behaviour and exist only to attribute bytes; nothing here is shippable.

An ablation that collapses the excess toward the 16-byte noise band identifies
the construct carrying it. An ablation that leaves the excess intact exonerates
the construct it removed.

Usage: bisect_attn.py KERNEL_DIR WORKDIR OUT_TSV
"""
import os
import re
import subprocess
import sys

kdir, work, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(work, exist_ok=True)
preamble = open(f"{HERE}/../../../research/r92-runs/router-recon/preamble.metal").read()

SLIDING = "laguna_sliding_fused_attn_ring_v1"
GROW = "laguna_full_fused_attn_grow_v1"


def sub1(text, old, new, count=1):
    """Replace and assert the edit actually applied."""
    n = text.count(old)
    if n < count:
        raise SystemExit(f"pattern not found ({n} < {count}): {old[:70]!r}")
    return text.replace(old, new, count)


def drop_range(text, start_pat, end_pat):
    lines = text.split("\n")
    s = next(i for i, l in enumerate(lines) if re.search(start_pat, l))
    e = next(i for i, l in enumerate(lines) if i > s and re.search(end_pat, l))
    return "\n".join(lines[:s] + lines[e + 1:])


def ring_sub_const_false(src):
    """Make the ring-wraparound predicate a compile-time constant."""
    src = re.sub(r"const bool sub_a = [^;]+;", "const bool sub_a = false;", src)
    src = re.sub(r"const bool sub_b = [^;]+;", "const bool sub_b = false;", src)
    return src


def ring_branch_false(src):
    """Keep the predicate computation, remove the substitute branch bodies."""
    return src.replace("if (substitute) {", "if (false) {")


def rope_dead(src):
    """Make the rotary/QK-norm prologue unreachable without unbalancing braces."""
    return sub1(src, "if (sg < 3) {", "if (false) {")


def size_t_to_uint(src):
    """Narrow the KV-cache address arithmetic from 64-bit to 32-bit.

    window*head_dim is 65536 and kv_head < 8, so every product here fits in
    uint32 by a wide margin; this is the one ablation that is also a candidate
    shippable rewrite rather than purely attributive.
    """
    return src.replace("(size_t)", "(uint)")


def loop_n(val):
    def f(src):
        return sub1(src, "constexpr int N = 512;", f"constexpr int N = {val};")
    return f


def rescale_plain(src):
    """Drop the bit-cast integer compare guarding the online-softmax rescale.

    LAGUNA_RESCALE tests as_type<uint>(delta) == 0u, an integer-ALU compare in
    the hot loop, twice per iteration.
    """
    return sub1(src, "if (as_type<uint>(db_delta_) == 0u) {", "if (false) {")


def no_simd_sum(src):
    """Remove the simdgroup shuffle-reduction."""
    return re.sub(r"simd_sum\(([^()]*)\)", r"(\1)", src)


def no_fast_exp(src):
    """Replace the transcendental with a plain multiply to test exp lowering."""
    return re.sub(r"metal::fast::exp\(([^;]*?)\)(\s*[;,)])", r"(\1)\2", src)


def no_simd_sum_loop(src):
    """Remove only the hot-loop score reductions, keeping every other site."""
    out = re.sub(r"((?:pair|pipeb)_score[01]) = simd_sum\(\1\);", r"\1 = (\1);",
                 src)
    if out == src:
        raise SystemExit("no hot-loop simd_sum matched")
    return out


def no_simd_sum_epilogue(src):
    """Remove only the epilogue reductions, keeping the hot-loop sites."""
    out = re.sub(r"simd_sum\((sum_exp_scores\[[^]]*\] \* pair_global_factor[01])\)",
                 r"(\1)", src)
    out = re.sub(r"simd_sum\((pair_v[01]\.[xyzw] \* pair_global_factor[01])\)",
                 r"(\1)", out)
    if out == src:
        raise SystemExit("no epilogue simd_sum matched")
    return out


def no_simd_sum_prologue(src):
    """Remove the QK-norm RMS reduction in the rotary prologue."""
    return sub1(src, "sum = simd_sum(sum);", "sum = (sum);")


def no_simd_max(src):
    return re.sub(r"simd_max\(([^()]*)\)", r"(\1)", src)


LADDER_HELPER = """
template <typename T>
inline T laguna_ladder_sum(T v) {
    v += simd_shuffle_xor(v, 1u);
    v += simd_shuffle_xor(v, 2u);
    v += simd_shuffle_xor(v, 4u);
    v += simd_shuffle_xor(v, 8u);
    v += simd_shuffle_xor(v, 16u);
    return v;
}
"""


def simd_sum_ladder(src):
    """Hand-lower every 32-lane reduction as an explicit xor butterfly.

    BD is 32 in both kernels, so five xor stages are a complete reduction. The
    order of a builtin simd_sum is unspecified, so this is bit-exact only if the
    builtin lowers to the same butterfly; treat as attributive until checked.
    """
    return LADDER_HELPER + re.sub(r"\bsimd_sum\(", "laguna_ladder_sum(", src)


def epilogue_vec_simd_sum(src):
    """Fuse the four componentwise output reductions into one vector reduction.

    Metal's simd_sum has a vector overload that reduces each component
    independently, so this changes the number of reduction calls without
    changing per-component arithmetic.
    """
    out = src
    for half in ("0", "1"):
        old = "".join(
            f"U acc{half}{i} = simd_sum(pair_v{half}.{c} * "
            f"pair_global_factor{half});\n"
            for i, c in enumerate("xyzw"))
        new = (f"float4 accv{half} = simd_sum(pair_v{half} * "
               f"pair_global_factor{half});\n"
               + "".join(f"U acc{half}{i} = accv{half}.{c};\n"
                         for i, c in enumerate("xyzw")))
        out = sub1(out, old, new)
    return out


ABLATIONS = {
    "base": lambda s: s,
    "ring_pred_const": ring_sub_const_false,
    "ring_branch_dead": ring_branch_false,
    "ring_both": lambda s: ring_branch_false(ring_sub_const_false(s)),
    "rope_prologue_dead": rope_dead,
    "addr_uint32": size_t_to_uint,
    "rescale_bitcast_dead": rescale_plain,
    "no_simd_sum": no_simd_sum,
    "no_simd_sum_loop": no_simd_sum_loop,
    "no_simd_sum_epilogue": no_simd_sum_epilogue,
    "no_simd_sum_prologue": no_simd_sum_prologue,
    "no_simd_max": no_simd_max,
    "simd_sum_ladder": simd_sum_ladder,
    "epilogue_vec_simd_sum": epilogue_vec_simd_sum,
    "no_fast_exp": no_fast_exp,
    "N_128": loop_n(128),
    "N_256": loop_n(256),
    "N_1024": loop_n(1024),
}

rows = []
for kernel in (SLIDING, GROW):
    src0 = open(f"{kdir}/{kernel}.gen.metal").read()
    for name, fn in ABLATIONS.items():
        try:
            src = fn(src0)
        except SystemExit as e:
            print(f"skip {kernel}/{name}: {e}", file=sys.stderr)
            continue
        if name != "base" and src == src0:
            print(f"skip {kernel}/{name}: ablation was a no-op", file=sys.stderr)
            continue
        path = f"{work}/{kernel}__{name}.metal"
        open(path, "w").write(preamble + src)
        res = subprocess.run(["bash", f"{HERE}/census.sh", path],
                             capture_output=True, text=True)
        got = {}
        for line in res.stdout.splitlines()[1:]:
            f = line.split("\t")
            if len(f) >= 3 and f[2].isdigit():
                got[f[0]] = int(f[2])
        if len(got) != 2:
            print(f"FAIL {kernel}/{name}: {res.stdout!r} {res.stderr[-400:]}",
                  file=sys.stderr)
            rows.append((kernel, name, None, None))
            continue
        rows.append((kernel, name, got["applegpu_g16s"], got["applegpu_g17s"]))

with open(out_path, "w") as fh:
    fh.write("kernel\tablation\tg16s\tg17s\tdelta\n")
    for k, n, a, b in rows:
        d = "" if a is None else str(b - a)
        fh.write(f"{k}\t{n}\t{a}\t{b}\t{d}\n")

print(f"{'kernel':<34}{'ablation':<20}{'g16s':>7}{'g17s':>7}{'delta':>8}"
      f"{'vs base':>10}")
base = {k: (a, b) for k, n, a, b in rows if n == "base"}
for k, n, a, b in rows:
    if a is None:
        print(f"{k:<34}{n:<20}{'COMPILE/NT FAIL':>32}")
        continue
    d = b - a
    bd = base[k][1] - base[k][0]
    print(f"{k:<34}{n:<20}{a:>7}{b:>7}{d:>+8}"
          f"{'' if n == 'base' else format(d - bd, '+d'):>10}")
