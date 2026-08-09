#!/usr/bin/env python3
"""Research-only. Build ablation variants of the sliding fused attention kernel
from the round-98 base source so `nezuko_r98_ab_kernel_probe.swift` can price
each mechanism separately.

Every edit is confined to the byte range of the sliding kernel literal (up to
the `laguna_full_fused_attn_grow_v1` declaration), so the full-attention kernel
is never touched and an accidentally ambiguous anchor fails loudly.

  python3 research/nezuko_r98_make_variants.py <base-source.swift> <outdir>
"""
import sys
import pathlib

PTR_DECL = """const device bfloat* pair_keys = k_cache +
    (size_t)kv_head * (window * head_dim) +
    (size_t)sg * head_dim + lane * qk_per_thread;
const device bfloat* pair_values = v_cache +
    (size_t)kv_head * (window * head_dim) +
    (size_t)sg * head_dim + lane * v_per_thread;
"""

BARRIER_ANCHOR = """} else if (sg == 3) {
    const device bfloat* vin = raw_values + kv_head * head_dim;
    for (uint i = lane; i < head_dim; i += 32) {
        tg_v[i] = vin[i];
    }
}
threadgroup_barrier(mem_flags::mem_threadgroup);
"""

PREFETCH = """const bool pre_sub = (uint(sg) == widx);
U pre_k[qk_per_thread];
bfloat pre_v0 = 0, pre_v1 = 0, pre_v2 = 0, pre_v3 = 0;
if (!pre_sub) {
    const vec<bfloat, 4> pre_kv_ =
        *reinterpret_cast<const device vec<bfloat, 4>*>(pair_keys);
    pre_k[0] = pre_kv_.x;
    pre_k[1] = pre_kv_.y;
    pre_k[2] = pre_kv_.z;
    pre_k[3] = pre_kv_.w;
    const vec<bfloat, 4> pre_vv_ =
        *reinterpret_cast<const device vec<bfloat, 4>*>(pair_values);
    pre_v0 = pre_vv_.x;
    pre_v1 = pre_vv_.y;
    pre_v2 = pre_vv_.z;
    pre_v3 = pre_vv_.w;
}
"""

LOOP_K_BASE = "    T_LOAD_K(pipe_ka, sub_a, pair_keys);\n"
LOOP_K_BRANCH = """    if (pre_live) {
        pipe_ka[0] = pre_k[0];
        pipe_ka[1] = pre_k[1];
        pipe_ka[2] = pre_k[2];
        pipe_ka[3] = pre_k[3];
    } else {
        T_LOAD_K(pipe_ka, sub_a, pair_keys);
    }
"""
LOOP_V_BASE = """    T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_a,
        pair_values);
"""
LOOP_V_BRANCH = """    if (pre_live) {
        pipe_va0 = pre_v0;
        pipe_va1 = pre_v1;
        pipe_va2 = pre_v2;
        pipe_va3 = pre_v3;
        pre_live = false;
    } else {
        T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_a,
            pair_values);
    }
"""
LOOP_HEAD = "int i = sg;\nfor (; i + 3 * BN < N; i += 4 * BN) {\n"


def sub1(text, old, new, what):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"anchor `{what}` matched {n} times, expected 1")
    return text.replace(old, new)


def split_sliding(src):
    cut = src.index('name: "laguna_full_fused_attn_grow_v1"')
    return src[:cut], src[cut:]


def hoist_pointers(sliding):
    """Move the phase-2 pointer computation ahead of the phase-1 barrier."""
    s = sub1(sliding, PTR_DECL, "", "pair pointer declaration")
    return sub1(s, BARRIER_ANCHOR,
                BARRIER_ANCHOR.replace(
                    "threadgroup_barrier(mem_flags::mem_threadgroup);\n",
                    "\n" + PTR_DECL
                    + "\nthreadgroup_barrier(mem_flags::mem_threadgroup);\n"),
                "phase-1 barrier")


VARIANTS = {}


def variant(fn):
    VARIANTS[fn.__name__] = fn
    return fn


@variant
def v2_ptr_hoist_only(sliding):
    """Pointer liveness across the barrier, with no prefetch and no new branch."""
    return hoist_pointers(sliding)


@variant
def v3_branch_only(sliding):
    """The in-loop branch and its extra registers, with no pre-barrier load.

    `pre_live` is seeded from a runtime value the compiler cannot fold, and the
    prefetch reads the same address the loop would read anyway, so this prices
    the loop restructuring alone against v1's restructuring-plus-earlier-issue.
    """
    s = hoist_pointers(sliding)
    s = sub1(s, BARRIER_ANCHOR.replace(
        "threadgroup_barrier(mem_flags::mem_threadgroup);\n",
        "\n" + PTR_DECL + "\nthreadgroup_barrier(mem_flags::mem_threadgroup);\n"),
        BARRIER_ANCHOR.replace(
            "threadgroup_barrier(mem_flags::mem_threadgroup);\n",
            "\n" + PTR_DECL + "\nconst bool pre_sub = (uint(sg) == widx);\n"
            "U pre_k[qk_per_thread];\n"
            "bfloat pre_v0 = 0, pre_v1 = 0, pre_v2 = 0, pre_v3 = 0;\n"
            "threadgroup_barrier(mem_flags::mem_threadgroup);\n"
            "if (!pre_sub) {\n"
            "    const vec<bfloat, 4> pre_kv_ =\n"
            "        *reinterpret_cast<const device vec<bfloat, 4>*>(pair_keys);\n"
            "    pre_k[0] = pre_kv_.x;\n"
            "    pre_k[1] = pre_kv_.y;\n"
            "    pre_k[2] = pre_kv_.z;\n"
            "    pre_k[3] = pre_kv_.w;\n"
            "    const vec<bfloat, 4> pre_vv_ =\n"
            "        *reinterpret_cast<const device vec<bfloat, 4>*>(pair_values);\n"
            "    pre_v0 = pre_vv_.x;\n"
            "    pre_v1 = pre_vv_.y;\n"
            "    pre_v2 = pre_vv_.z;\n"
            "    pre_v3 = pre_vv_.w;\n"
            "}\n"),
        "barrier for post-barrier prefetch")
    s = sub1(s, LOOP_HEAD, "bool pre_live = !pre_sub;\n" + LOOP_HEAD, "loop head")
    s = sub1(s, LOOP_K_BASE, LOOP_K_BRANCH, "loop K load")
    return sub1(s, LOOP_V_BASE, LOOP_V_BRANCH, "loop V load")


@variant
def v1_pre_barrier_prefetch(sliding):
    """The shipped arm-B implementation: hoisted pointers, pre-barrier load,
    branch-selected consumption on the first trip."""
    s = hoist_pointers(sliding)
    s = sub1(s, "\nthreadgroup_barrier(mem_flags::mem_threadgroup);\n\nif ((head0 % gqa) == 0",
             "\n" + PREFETCH + "threadgroup_barrier(mem_flags::mem_threadgroup);\n\n"
             "if ((head0 % gqa) == 0", "prefetch insertion point")
    s = sub1(s, LOOP_HEAD, "bool pre_live = !pre_sub;\n" + LOOP_HEAD, "loop head")
    s = sub1(s, LOOP_K_BASE, LOOP_K_BRANCH, "loop K load")
    return sub1(s, LOOP_V_BASE, LOOP_V_BRANCH, "loop V load")


LOOP_TAIL = """    pair_keys += 4 * inner_k_stride;
    pair_values += 4 * inner_v_stride;
}
"""
# The `a` sub-block's load is rotated to the bottom of the previous trip, so
# the loop body consumes it with no branch and no wait. `inner_k_stride` and
# `inner_v_stride` are the same expression, hence one advance for both. On the
# final trip the advance is clamped to zero: the address is re-read rather than
# run past the end of this KV head's ring, and the value is discarded.
LOOP_TAIL_ROTATED = """    const int pre_adv = (i + 7 * BN < N) ? 4 * inner_k_stride : 0;
    pair_keys += pre_adv;
    pair_values += pre_adv;
    const bool pre_next = uint(i + 4 * BN) == widx;
    T_LOAD_K(pre_k, pre_next, pair_keys);
    T_LOAD_V(pre_v0, pre_v1, pre_v2, pre_v3, pre_next, pair_values);
}
"""
LOOP_K_ROTATED = """    pipe_ka[0] = pre_k[0];
    pipe_ka[1] = pre_k[1];
    pipe_ka[2] = pre_k[2];
    pipe_ka[3] = pre_k[3];
"""
LOOP_V_ROTATED = """    pipe_va0 = pre_v0;
    pipe_va1 = pre_v1;
    pipe_va2 = pre_v2;
    pipe_va3 = pre_v3;
"""
PRE_DECL = """const bool pre_sub = (uint(sg) == widx);
U pre_k[qk_per_thread];
bfloat pre_v0 = 0, pre_v1 = 0, pre_v2 = 0, pre_v3 = 0;
"""
PRE_DEVICE_LOAD = """if (!pre_sub) {
    const vec<bfloat, 4> pre_kv_ =
        *reinterpret_cast<const device vec<bfloat, 4>*>(pair_keys);
    pre_k[0] = pre_kv_.x;
    pre_k[1] = pre_kv_.y;
    pre_k[2] = pre_kv_.z;
    pre_k[3] = pre_kv_.w;
    const vec<bfloat, 4> pre_vv_ =
        *reinterpret_cast<const device vec<bfloat, 4>*>(pair_values);
    pre_v0 = pre_vv_.x;
    pre_v1 = pre_vv_.y;
    pre_v2 = pre_vv_.z;
    pre_v3 = pre_vv_.w;
}
"""
PRE_TG_LOAD = """if (pre_sub) {
    pre_k[0] = tg_k[lane * qk_per_thread + 0];
    pre_k[1] = tg_k[lane * qk_per_thread + 1];
    pre_k[2] = tg_k[lane * qk_per_thread + 2];
    pre_k[3] = tg_k[lane * qk_per_thread + 3];
    pre_v0 = tg_v[lane * v_per_thread + 0];
    pre_v1 = tg_v[lane * v_per_thread + 1];
    pre_v2 = tg_v[lane * v_per_thread + 2];
    pre_v3 = tg_v[lane * v_per_thread + 3];
}
"""
BARRIER = "threadgroup_barrier(mem_flags::mem_threadgroup);\n"


def rotate_loop(s):
    s = sub1(s, LOOP_K_BASE, LOOP_K_ROTATED, "loop K load")
    s = sub1(s, LOOP_V_BASE, LOOP_V_ROTATED, "loop V load")
    return sub1(s, LOOP_TAIL, LOOP_TAIL_ROTATED, "loop tail")


@variant
def v4_rotated_pre_barrier(sliding):
    """Branchless rotation with the trip-0 prologue issued before the barrier.

    This is H-B proper: the only device load in the pre-barrier window, and the
    loop consumes it with no added control flow.
    """
    s = hoist_pointers(sliding)
    s = sub1(s, "\n" + BARRIER + "\nif ((head0 % gqa) == 0",
             "\n" + PRE_DECL + PRE_DEVICE_LOAD + BARRIER + PRE_TG_LOAD
             + "\nif ((head0 % gqa) == 0", "prologue insertion point")
    return rotate_loop(s)


@variant
def v5_rotated_post_barrier(sliding):
    """Identical to v4 except the prologue load is issued after the barrier.

    v5 minus base prices the loop rotation; v4 minus v5 prices the pre-barrier
    window alone, with instruction count, registers and control flow matched.
    """
    s = hoist_pointers(sliding)
    s = sub1(s, "\n" + BARRIER + "\nif ((head0 % gqa) == 0",
             "\n" + BARRIER + PRE_DECL
             + "T_LOAD_K(pre_k, pre_sub, pair_keys);\n"
             "T_LOAD_V(pre_v0, pre_v1, pre_v2, pre_v3, pre_sub, pair_values);\n"
             + "\nif ((head0 % gqa) == 0", "prologue insertion point")
    return rotate_loop(s)


def main():
    base = pathlib.Path(sys.argv[1]).read_text()
    outdir = pathlib.Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    sliding, rest = split_sliding(base)
    for name, fn in VARIANTS.items():
        out = outdir / f"{name}.swift"
        out.write_text(fn(sliding) + rest)
        print(f"{out}  ({len(out.read_text())} B)")


if __name__ == "__main__":
    main()
