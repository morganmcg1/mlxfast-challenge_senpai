import pathlib

src = pathlib.Path('/tmp/r107f/dr_shipped.metal').read_text()

stage_old = "for (uint i = 0; i < values_per_lane / 4; ++i) {"
assert stage_old in src
pragma = "#pragma clang loop unroll(full)\n"

u1 = src.replace(stage_old, pragma + stage_old)
pathlib.Path('/tmp/r107f/dr_u1.metal').write_text(u1)

row_old = "for (uint row = 0; row < outputs_per_simd; ++row) {"
n = u1.count(row_old)
u2 = u1.replace(row_old, pragma + row_old)
pathlib.Path('/tmp/r107f/dr_u2.metal').write_text(u2)
print("row loops found:", n, "total pragmas u2:", u2.count("unroll(full)"))
