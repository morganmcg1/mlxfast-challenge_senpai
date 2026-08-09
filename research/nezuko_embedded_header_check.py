#!/usr/bin/env python3
"""Find AOT headers whose body is embedded verbatim in an mlx-generated twin.

Tests/MLXFastTests/NVFP4QuantizedMMTests.swift asserts that the body of
kernels/fp4.h appears, byte for byte, inside mlx-generated/fp_quantized.cpp.
The generated .cpp files are `#include`-expanded snapshots of the AOT headers,
so editing a header without editing its snapshot breaks that structural
invariant even when the edit is comment-only and cannot change compiled code.

    nezuko_embedded_header_check.py BASE_SHA
    nezuko_embedded_header_check.py --exclusions BASE_SHA

Reports, for every kernels/ header, whether its BASE_SHA body is embedded in a
generated .cpp and whether the working-tree body still is. A header that was
embedded at base but is not embedded now must be reverted or its snapshot
updated in lockstep.

--exclusions derives the do-not-touch set from BASE_SHA alone, so the strip
pipeline is reproducible without depending on the current working tree.
"""

import glob
import os
import subprocess
import sys

GEN = "Vendor/mlx-swift/Source/Cmlx/mlx-generated"
KERNELS = "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels"


def show(sha, path):
    r = subprocess.run(["git", "show", f"{sha}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def body(text, drop=2):
    return "\n".join(text.split("\n")[drop:])


def base_state(sha):
    gen_old = "\n".join(show(sha, q) or "" for q in sorted(glob.glob(f"{GEN}/*.cpp")))
    gen_old_lines = set(gen_old.split("\n"))
    out = {}
    for p in sorted(
        glob.glob(f"{KERNELS}/**/*.h", recursive=True)
        + glob.glob(f"{KERNELS}/**/*.metal", recursive=True)
    ):
        old = show(sha, p)
        if old is None:
            continue
        lines = [ln for ln in old.split("\n") if ln.strip()]
        share = sum(ln in gen_old_lines for ln in lines) / max(len(lines), 1)
        out[p] = (share, body(old) in gen_old, old)
    return gen_old, out


def cmd_exclusions(sha):
    _, base = base_state(sha)
    excluded = sorted(p for p, (share, embedded, _) in base.items() if share >= 0.90 or embedded)
    print(f"# embedded-twin exclusions derived from {sha}", file=sys.stderr)
    print(f"# {len(excluded)} AOT sources whose base body is snapshotted into mlx-generated/*.cpp", file=sys.stderr)
    for p in excluded:
        print(p)
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--exclusions":
        return cmd_exclusions(sys.argv[2])
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    sha = sys.argv[1]
    gen_now = "\n".join(
        open(p, encoding="utf-8").read() for p in sorted(glob.glob(f"{GEN}/*.cpp"))
    )
    headers = sorted(
        p
        for p in glob.glob(f"{KERNELS}/**/*.h", recursive=True)
        + glob.glob(f"{KERNELS}/**/*.metal", recursive=True)
    )
    gen_old = "\n".join(show(sha, q) or "" for q in sorted(glob.glob(f"{GEN}/*.cpp")))
    gen_old_lines = set(gen_old.split("\n"))
    rows = []
    for p in headers:
        old = show(sha, p)
        if old is None:
            continue
        new = open(p, encoding="utf-8").read()
        if old == new:
            continue
        # Line-overlap is the wide net: exact body containment misses a header
        # whose snapshot was taken with a different leading-line trim.
        lines = [ln for ln in old.split("\n") if ln.strip()]
        share = sum(ln in gen_old_lines for ln in lines) / max(len(lines), 1)
        exact_before = body(old) in gen_old
        exact_after = body(new) in gen_now
        rows.append((share, exact_before, exact_after, p))
    rows.sort(reverse=True)
    print(f"changed AOT sources: {len(rows)}")
    print(f"{'share':>6}  {'base':>5}  {'now':>5}  path")
    risky = []
    for share, eb, ea, p in rows:
        if share > 0.0:
            print(f"{share:6.2f}  {str(eb):>5}  {str(ea):>5}  {p}")
        if share >= 0.90 or (eb and not ea):
            risky.append(p)
    print(f"\nembedded-twin risk (share>=0.90 or lost exact containment): {len(risky)}")
    for p in risky:
        print(f"  {p}")
    return 1 if risky else 0


if __name__ == "__main__":
    sys.exit(main())
