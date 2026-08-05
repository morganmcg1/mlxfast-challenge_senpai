import shutil

src = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
p = "/tmp/cand8.swift"
shutil.copyfile(src, p)
lines = open(p, encoding="utf-8").read().split("\n")
assert lines[1529] == "        int i = sg;", repr(lines[1529])
assert lines[1530].startswith("        for (; i + 3 * BN < N;"), repr(lines[1530])

D = 8
letters = "abcdefgh"[:D]
out = ["        for (; i + %d * BN < N; i += %d * BN) {" % (D - 1, D)]
for j, L in enumerate(letters):
    if j == 0:
        out.append("            const device bfloat* p8k_a = pair_keys;")
        out.append("            const device bfloat* p8v_a = pair_values;")
    else:
        out.append("            const device bfloat* p8k_%s = pair_keys + %d * inner_k_stride;" % (L, j))
        out.append("            const device bfloat* p8v_%s = pair_values + %d * inner_v_stride;" % (L, j))
for j, L in enumerate(letters):
    out.append("            const bool p8s_%s = uint(i + %d * BN) == widx;" % (L, j))
for L in letters:
    out.append("            U p8kk_%s[4];" % L)
for L in letters:
    out.append("            T_LOAD_K(p8kk_%s, p8s_%s, p8k_%s);" % (L, L, L))
for L in letters:
    out.append("            bfloat p8w_%s0, p8w_%s1, p8w_%s2, p8w_%s3;" % (L, L, L, L))
for L in letters:
    out.append("            T_LOAD_V(p8w_%s0, p8w_%s1, p8w_%s2, p8w_%s3, p8s_%s, p8v_%s);" % (L, L, L, L, L, L))
for L in letters:
    out.append("            T_SLOT(p8kk_%s, p8w_%s0, p8w_%s1, p8w_%s2, p8w_%s3);" % (L, L, L, L, L))
out.append("            pair_keys += %d * inner_k_stride;" % D)
out.append("            pair_values += %d * inner_v_stride;" % D)
out.append("        }")

lines[1530:1530] = out
open(p, "w", encoding="utf-8").write("\n".join(lines))
print("wrote", p, "depth", D, "inserted lines", len(out))
