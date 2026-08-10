import pathlib

src = pathlib.Path('/tmp/r107f/dr_shipped.metal').read_text()
old = "constexpr uint outputs_per_simd = 4;"
assert old in src
for n in (8, 16):
    out = src.replace(old, "constexpr uint outputs_per_simd = %d;" % n)
    pathlib.Path('/tmp/r107f/dr_opsi%d.metal' % n).write_text(out)
print("ok")
