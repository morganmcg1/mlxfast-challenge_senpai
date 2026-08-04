"""Generate h-sweep and inner-loop cost-attribution variants of pass 1.

usage: python3 diag_pass1.py probe_p1.metal

Pass 1 has a single un-pipelined slot loop, so a one-line textual delta isolates
one term of the inner loop without disturbing the rest of the instruction
stream. Every `-` variant below produces deliberately wrong output; only its
timing is meaningful.

  probe_p1h<H>.metal      heads per threadgroup H in {1,2,4,8}; H=2 issues the
                          same K/V bytes as the shipped kernel, H=8 issues 4x
                          fewer. Dispatch with groups = (64/H) * 4.
  probe_p1h<H>-nosum      the QK cross-lane reduction `simd_sum` deleted
  probe_p1h<H>-nosoftmax  running max / rescale / exp deleted, simd_sum kept
  probe_p1h<H>-noorescale the four output-rescale multiplies deleted
  probe_p1h<H>-noqk       the four QK multiply-adds deleted, simd_sum kept
"""
import sys

src = open(sys.argv[1]).read()

SUM = "                pair_score = simd_sum(pair_score);\n"
SOFTMAX = """                U pair_new_max = metal::max(pair_max[h], pair_score);
                U pair_factor;
                LAGUNA_RESCALE(pair_factor, pair_max[h] - pair_new_max);
                U pair_exp = metal::fast::exp(pair_score - pair_new_max);

                pair_max[h] = pair_new_max;
                pair_sum[h] = pair_sum[h] * pair_factor + pair_exp;
"""
SOFTMAX_STUB = """                U pair_factor = pair_score;
                U pair_exp = pair_score;
                pair_max[h] = pair_score;
                pair_sum[h] = pair_sum[h] + pair_exp;
"""
QK = """                pair_score += pair_q[h][0] * pipe_k[0];
                pair_score += pair_q[h][1] * pipe_k[1];
                pair_score += pair_q[h][2] * pipe_k[2];
                pair_score += pair_q[h][3] * pipe_k[3];
"""
QK_STUB = "                pair_score += pipe_k[h & 3];\n"
ORESCALE = """                pair_o[h][0] = pair_o[h][0] * pair_factor + pair_exp * pipe_v0;
                pair_o[h][1] = pair_o[h][1] * pair_factor + pair_exp * pipe_v1;
                pair_o[h][2] = pair_o[h][2] * pair_factor + pair_exp * pipe_v2;
                pair_o[h][3] = pair_o[h][3] * pair_factor + pair_exp * pipe_v3;
"""
ORESCALE_STUB = """                pair_o[h][0] = pair_o[h][0] + pair_exp * pipe_v0;
                pair_o[h][1] = pair_o[h][1] + pair_exp * pipe_v1;
                pair_o[h][2] = pair_o[h][2] + pair_exp * pipe_v2;
                pair_o[h][3] = pair_o[h][3] + pair_exp * pipe_v3;
"""

DELTAS = {
    "": [],
    "-nosum": [(SUM, "")],
    "-nosoftmax": [(SOFTMAX, SOFTMAX_STUB)],
    "-noorescale": [(ORESCALE, ORESCALE_STUB)],
    "-noqk": [(QK, QK_STUB)],
}

for heads in (1, 2, 4, 8):
    base = src.replace(
        "constexpr uint H = 8;", "constexpr uint H = %d;" % heads)
    assert heads == 8 or base != src
    for suffix, deltas in DELTAS.items():
        text = base
        for old, new in deltas:
            assert old in text, (heads, suffix)
            text = text.replace(old, new)
        name = "probe_p1h%d%s.metal" % (heads, suffix)
        open(name, "w").write(text)
        print("%s (%d bytes, groups %d)" % (name, len(text), (64 // heads) * 4))
