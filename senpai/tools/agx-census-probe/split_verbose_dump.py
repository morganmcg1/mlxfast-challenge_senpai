#!/usr/bin/env python3
"""Split an MLX verbose-dump log into one translation unit per custom kernel.

Input:  the stdout log produced by senpai/tools/agx-census-probe/run_verbose_dump.sh
        (MLX prints `Generated source code for \\`NAME\\`:` then a fenced block
        holding kernel_source -- metal_kernel.cpp:342-347).
Output: OUTDIR/<name>.gen.metal   header + signature + body, exactly what MLX
                                  stores in CustomKernel::source_
        OUTDIR/<name>.metal       metal::utils() + source_, i.e. the exact
                                  translation unit Device::build_library_
                                  compiles (custom_kernel.cpp:71)
        OUTDIR/manifest.tsv       name, occurrences, distinct_variants, gen_bytes

Every repeated emission of the same kernel name is compared byte-for-byte; a
name with more than one distinct variant is reported rather than silently
deduplicated, because MLX keys its library cache on kernel_name and recompiles
when the source for that name changes (custom_kernel.cpp:58-68).

Usage: split_verbose_dump.py LOG OUTDIR PREAMBLE
"""
import os
import re
import sys

log_path, outdir, preamble_path = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(outdir, exist_ok=True)
preamble = open(preamble_path).read()

START = re.compile(r"^Generated source code for `(.+)`:$")
FENCE = "```"

variants: dict[str, list[str]] = {}
counts: dict[str, int] = {}

with open(log_path, errors="replace") as fh:
    lines = fh.read().split("\n")

i = 0
while i < len(lines):
    m = START.match(lines[i])
    if not m or i + 1 >= len(lines) or lines[i + 1] != FENCE:
        i += 1
        continue
    name = m.group(1)
    j = i + 2
    buf = []
    while j < len(lines) and lines[j] != FENCE:
        buf.append(lines[j])
        j += 1
    if j >= len(lines):
        print(f"warning: unterminated block for {name}", file=sys.stderr)
        break
    # `<< kernel_source << std::endl` adds one newline beyond the source's own
    # trailing newline, so the fenced block ends with one spurious blank line.
    if buf and buf[-1] == "":
        buf.pop()
    src = "\n".join(buf) + "\n"
    counts[name] = counts.get(name, 0) + 1
    seen = variants.setdefault(name, [])
    if src not in seen:
        seen.append(src)
    i = j + 1

rows = []
for name in sorted(variants):
    for idx, src in enumerate(variants[name]):
        suffix = "" if idx == 0 else f".v{idx}"
        gen = os.path.join(outdir, f"{name}{suffix}.gen.metal")
        full = os.path.join(outdir, f"{name}{suffix}.metal")
        open(gen, "w").write(src)
        open(full, "w").write(preamble + src)
    rows.append((name, counts[name], len(variants[name]), len(variants[name][0])))

with open(os.path.join(outdir, "manifest.tsv"), "w") as fh:
    fh.write("name\toccurrences\tdistinct_variants\tgen_bytes\n")
    for r in rows:
        fh.write("\t".join(str(x) for x in r) + "\n")

multi = [r for r in rows if r[2] > 1]
print(f"kernels={len(rows)} emissions={sum(counts.values())} multi_variant={len(multi)}")
for r in multi:
    print(f"  MULTI {r[0]} variants={r[2]}")
