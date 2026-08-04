"""Generate bit-exact candidate variants of the shipped fused-attention kernel.

usage: python3 diag_epilogue.py probe_orig.metal

Unlike diag.py's bound-identification variants, every kernel written here must
produce byte-identical output; the probe's mismatch counter is the proof.

  probe_pad.metal          epilogue `outputs` stride BD -> BD+1, so the
                           transposing threadgroup write stops being a 32-way
                           bank conflict (write index lane*33+sg is distinct
                           mod 32 for every lane; the read stays contiguous)
  probe_padvec.metal       pad + both heads' QK cross-lane reductions issued as
                           one float2 `simd_sum` instead of two scalar ones
                           (measured: no gain, Metal lowers the float2 reduction
                           to the same two scalar butterflies)
"""
import sys

src = open(sys.argv[1]).read()


def write(name, text):
    open(name, "w").write(text)
    print("%s (%d bytes)" % (name, len(text)))


def pad(text):
    out = text.replace(
        "threadgroup U outputs[4 * BN * BD];",
        "constexpr int BDP = BD + 1;\n"
        "        threadgroup U outputs[4 * BN * BDP];")
    out = out.replace(
        "constexpr int pair_plane_size = BN * BD;",
        "constexpr int pair_plane_size = BN * BDP;")
    out = out.replace("lane * BD + sg", "lane * BDP + sg")
    out = out.replace("sg * BD + lane", "sg * BDP + lane")
    assert out.count("BDP") >= 5
    return out


def vector_reduce(text):
    out = text
    for name in ("pair", "pipeb"):
        old = ("            %s_score0 = simd_sum(%s_score0);\n"
               "            %s_score1 = simd_sum(%s_score1);"
               % (name, name, name, name))
        new = ("            {\n"
               "                const vec<U, 2> vs_ =\n"
               "                    simd_sum(vec<U, 2>(%s_score0, %s_score1));\n"
               "                %s_score0 = vs_.x;\n"
               "                %s_score1 = vs_.y;\n"
               "            }" % (name, name, name, name))
        if old in out:
            out = out.replace(old, new)
    assert "vec<U, 2> vs_" in out
    return out


padded = pad(src)
write("probe_pad.metal", padded)
write("probe_padvec.metal", vector_reduce(padded))
