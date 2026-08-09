#!/usr/bin/env python3
"""Insert `verbose: true` at every MLXFastKernel invocation site.

Research-only. MLX prints the fully generated MSL for a custom kernel from
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:342-347
when the invocation passes verbose=true. `MLXFast.metalKernel(...)` has no
verbose parameter; the flag lives on `callAsFunction`, after `outputDTypes:`
(and after `initValue:` when present -- LagunaRuntimeModel.swift uses neither
`initValue:` nor `stream:`), so the last labelled argument is always
`outputDTypes:`.

The printed text is header + signature + body WITHOUT the metal::utils()
preamble, which backend/metal/custom_kernel.cpp:71 prepends later.

Usage: python3 add_verbose_dump.py PATH...
"""
import sys

DEFAULT_PATHS = [
    "Sources/MLXFastModel/LagunaRuntimeModel.swift",
    "Sources/MLXFastModel/LagunaRuntimeLayers.swift",
    "Sources/MLXFastModel/LagunaLmHeadPrune.swift",
]


def patch(path):
    lines = open(path).read().split("\n")
    out, i, sites = [], 0, 0
    while i < len(lines):
        line = lines[i]
        if "outputDTypes:" not in line or "verbose: true" in line:
            out.append(line)
            i += 1
            continue
        sites += 1
        tail = line.split("outputDTypes:", 1)[1]
        if ")" in tail:
            idx = line.index(")", line.index("outputDTypes:"))
            out.append(line[:idx] + ", verbose: true" + line[idx:])
            i += 1
            continue
        out.append(line)
        i += 1
        while i < len(lines) and lines[i].lstrip().startswith("+ "):
            out.append(lines[i])
            i += 1
        closing = lines[i]
        assert closing.lstrip().startswith(")"), f"unexpected close at {i+1}: {closing!r}"
        indent = len(closing) - len(closing.lstrip())
        out[-1] += ","
        out.append(" " * (indent + 4) + "verbose: true")
        out.append(closing)
        i += 1
    open(path, "w").write("\n".join(out))
    print(f"patched {sites} invocation sites in {path}")
    return sites


total = sum(patch(p) for p in (sys.argv[1:] or DEFAULT_PATHS))
print(f"total {total} invocation sites")
