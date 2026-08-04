"""Part 0 of PR #36: does vector `simd_sum` stack with the shipped BDP padding?

usage: python3 diag_stack.py probe_b.metal

`probe_b.metal` is the shipped kernel rendered from the worktree (padding in,
scalar reductions). Every arm below is generated from that one text, so the
control is compile-identical apart from the mechanism under test.

  a_control    BDP = BD   (padding off), scalar simd_sum
  b_pad        BDP = BD+1 (shipped),     scalar simd_sum
  c_vec2       BDP = BD,                 float2 simd_sum over the head pair
  d_padvec2    BDP = BD+1,               float2 simd_sum over the head pair
  e_vec4       BDP = BD,                 float4 simd_sum over both pipe halves
  f_padvec4    BDP = BD+1,               float4 simd_sum over both pipe halves
  g_padvec4ep  f_padvec4 + vector simd_sum in the epilogue reductions

The float4 arms hoist the `pipe_kb` madds above the first softmax update so all
four QK scores are live at once. That reorders independent statements only: each
score's own addition chain, and each reduction tree, is untouched.
"""
import sys

src = open(sys.argv[1]).read()

PAD_ON = "constexpr int BDP = BD + 1;"
PAD_OFF = "constexpr int BDP = BD;"
assert src.count(PAD_ON) == 1


def write(name, text):
    open(name, "w").write(text)
    print("%s (%d bytes)" % (name, len(text)))


def unpad(text):
    return text.replace(PAD_ON, PAD_OFF)


def block(text, start, end):
    """Exact substring from `start` through the end of the line holding `end`."""
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[i:j]


def vec2(text):
    """One float2 simd_sum per pipe half instead of two scalar ones."""
    out = text
    for name in ("pair", "pipeb"):
        old = ("            %s_score0 = simd_sum(%s_score0);\n"
               "            %s_score1 = simd_sum(%s_score1);"
               % (name, name, name, name))
        assert old in out, name
        new = ("            {\n"
               "                const vec<U, 2> vs_ =\n"
               "                    simd_sum(vec<U, 2>(%s_score0, %s_score1));\n"
               "                %s_score0 = vs_.x;\n"
               "                %s_score1 = vs_.y;\n"
               "            }" % (name, name, name, name))
        out = out.replace(old, new)
    return out


def vec4(text):
    """Hoist the second half's madds and reduce all four scores at once."""
    madds_b = block(
        text, "            U pipeb_score0 = 0;",
        "            pipeb_score1 += pair_q1[3] * pipe_kb[3];\n")
    reduce_b = ("            pipeb_score0 = simd_sum(pipeb_score0);\n"
                "            pipeb_score1 = simd_sum(pipeb_score1);\n")
    reduce_a = ("            pair_score0 = simd_sum(pair_score0);\n"
                "            pair_score1 = simd_sum(pair_score1);\n")
    assert text.count(madds_b) == 1
    assert text.count(reduce_b) == 1
    assert text.count(reduce_a) == 1

    fused = madds_b + (
        "            {\n"
        "                const vec<U, 4> vs_ = simd_sum(vec<U, 4>(\n"
        "                    pair_score0, pair_score1,\n"
        "                    pipeb_score0, pipeb_score1));\n"
        "                pair_score0 = vs_.x;\n"
        "                pair_score1 = vs_.y;\n"
        "                pipeb_score0 = vs_.z;\n"
        "                pipeb_score1 = vs_.w;\n"
        "            }\n")
    out = text.replace(madds_b, "").replace(reduce_b, "")
    out = out.replace(reduce_a, fused)
    return out


COMBINE_HEAD = """        for (int p = 0; p < pair_planes; ++p) {
            U acc0 = simd_sum(
                outputs[p * pair_plane_size + sg * BDP + lane] *
                pair_global_factor0);
            U acc1 = simd_sum(
                outputs[
                    (pair_planes + p) * pair_plane_size + sg * BDP + lane] *
                pair_global_factor1);
"""

COMBINE_TAILS = (
    ("""            pair_o0[p] = pair_sum0 == 0 ? acc0 : (acc0 / pair_sum0);
            pair_o1[p] = pair_sum1 == 0 ? acc1 : (acc1 / pair_sum1);
        }
""", 0),
    ("""            pair_o0[pair_planes + p] =
                pair_sum0 == 0 ? acc0 : (acc0 / pair_sum0);
            pair_o1[pair_planes + p] =
                pair_sum1 == 0 ? acc1 : (acc1 / pair_sum1);
        }
""", 2),
)


def epilogue_vec(text):
    """Pack the epilogue's cross-lane reductions into float2/float4 sums."""
    old_sums = (
        "        pair_sum0 = simd_sum(sum_exp_scores[lane] * pair_global_factor0);\n"
        "        pair_sum1 = simd_sum(sum_exp_scores[BN + lane] * pair_global_factor1);\n")
    assert text.count(old_sums) == 1
    new_sums = (
        "        {\n"
        "            const vec<U, 2> vs_ = simd_sum(vec<U, 2>(\n"
        "                sum_exp_scores[lane] * pair_global_factor0,\n"
        "                sum_exp_scores[BN + lane] * pair_global_factor1));\n"
        "            pair_sum0 = vs_.x;\n"
        "            pair_sum1 = vs_.y;\n"
        "        }\n")
    out = text.replace(old_sums, new_sums)

    # pair_planes == 2, so each combine loop is four scalar simd_sums over the
    # same exchange buffer and one float4 covers both planes and both heads.
    for tail, base in COMBINE_TAILS:
        old = COMBINE_HEAD + tail
        assert out.count(old) == 1, tail[:40]
        new = (
            "        {\n"
            "            const vec<U, 4> vs_ = simd_sum(vec<U, 4>(\n"
            "                outputs[0 * pair_plane_size + sg * BDP + lane] *\n"
            "                    pair_global_factor0,\n"
            "                outputs[(pair_planes + 0) * pair_plane_size +\n"
            "                    sg * BDP + lane] * pair_global_factor1,\n"
            "                outputs[1 * pair_plane_size + sg * BDP + lane] *\n"
            "                    pair_global_factor0,\n"
            "                outputs[(pair_planes + 1) * pair_plane_size +\n"
            "                    sg * BDP + lane] * pair_global_factor1));\n"
            "            pair_o0[%d] = pair_sum0 == 0 ? vs_.x : (vs_.x / pair_sum0);\n"
            "            pair_o1[%d] = pair_sum1 == 0 ? vs_.y : (vs_.y / pair_sum1);\n"
            "            pair_o0[%d] = pair_sum0 == 0 ? vs_.z : (vs_.z / pair_sum0);\n"
            "            pair_o1[%d] = pair_sum1 == 0 ? vs_.w : (vs_.w / pair_sum1);\n"
            "        }\n" % (base, base, base + 1, base + 1))
        out = out.replace(old, new)
    return out


padded = src
plain = unpad(src)
write("probe_a.metal", plain)
write("probe_b.metal", padded)
write("probe_c.metal", vec2(plain))
write("probe_d.metal", vec2(padded))
write("probe_e.metal", vec4(plain))
write("probe_f.metal", vec4(padded))
write("probe_g.metal", epilogue_vec(vec4(padded)))
