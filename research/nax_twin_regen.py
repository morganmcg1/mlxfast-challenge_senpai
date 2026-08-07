#!/usr/bin/env python3
"""Regenerate an mlx-generated/*.cpp twin from its Metal header.

research/nax_twin_check.py defines the only legal differences between a kernel
header and the R"preamble( ... )preamble" copy the runtime actually compiles:
generator boilerplate around the header text, whole-run deletions of #include
lines, and whole-run deletions of // PRAGMA-VARIANT comment blocks. That rule
is mechanical, so the twin can be rebuilt from the header instead of patched by
hand twice -- which is where staleness comes from.

The transform is validated before it is used: the boilerplate prefix/suffix are
read off a reference commit's own header/twin pair, and prefix + strip(header)
+ suffix must reproduce that commit's embedded block exactly. Only then is the
working-tree twin rewritten.

Usage: research/nax_twin_regen.py --base REV [stem ...]
"""

import argparse
import difflib
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
HDR_REL = "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels"
GEN_REL = "Vendor/mlx-swift/Source/Cmlx/mlx-generated"

# Only the project-local includes are inlined into the boilerplate prefix; the
# <metal_*> system includes survive into the embedded source.
LOCAL_INCLUDE_RE = re.compile(r'\s*#include\s*"')
COMMENT_RE = re.compile(r"\s*//")


def strip_header(lines):
    out, i = [], 0
    while i < len(lines):
        if LOCAL_INCLUDE_RE.match(lines[i]):
            i += 1
            continue
        if COMMENT_RE.match(lines[i]) and "PRAGMA-VARIANT" in lines[i]:
            while i < len(lines) and COMMENT_RE.match(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def split_twin(text, stem):
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if 'R"preamble(' in l]
    ends = [i for i, l in enumerate(lines) if ')preamble";' in l]
    if not starts or not ends:
        raise SystemExit(f'{stem}: no R"preamble( ... )preamble" block')
    return lines[: starts[0] + 1], lines[starts[0] + 1 : ends[0]], lines[ends[0] :]


def show(rev, rel):
    return subprocess.run(
        ["git", "show", f"{rev}:{rel}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def boilerplate(hdr, inner, stem, rev):
    ops = difflib.SequenceMatcher(None, hdr, inner, autojunk=False).get_opcodes()
    prefix = inner[ops[0][3] : ops[0][4]] if ops[0][:3] == ("insert", 0, 0) else []
    last = ops[-1]
    suffix = (
        inner[last[3] : last[4]] if last[0] == "insert" and last[2] == len(hdr) else []
    )
    rebuilt = prefix + strip_header(hdr) + suffix
    if rebuilt != inner:
        for i, (a, b) in enumerate(zip(rebuilt, inner)):
            if a != b:
                raise SystemExit(
                    f"{stem}: transform does not reproduce the {rev} twin at "
                    f"block line {i}\n  rebuilt | {a}\n  actual  | {b}"
                )
        raise SystemExit(
            f"{stem}: transform length mismatch at {rev}: "
            f"{len(rebuilt)} vs {len(inner)}"
        )
    return prefix, suffix


def regen(stem, base):
    gen = ROOT / GEN_REL / f"{stem}.cpp"
    hdr = ROOT / HDR_REL / f"{stem}.h"

    _, base_inner, _ = split_twin(show(base, f"{GEN_REL}/{stem}.cpp"), stem)
    prefix, suffix = boilerplate(
        show(base, f"{HDR_REL}/{stem}.h").splitlines(), base_inner, stem, base
    )

    old = gen.read_text()
    head, inner, tail = split_twin(old, stem)
    if inner[: len(prefix)] != prefix or (suffix and inner[-len(suffix) :] != suffix):
        raise SystemExit(f"{stem}: working twin boilerplate differs from {base}")

    body = prefix + strip_header(hdr.read_text().splitlines()) + suffix
    new = "\n".join(head + body + tail) + "\n"
    if new == old:
        print(f"{stem}: twin already current")
        return
    gen.write_text(new)
    print(f"{stem}: twin regenerated from header ({len(new)} bytes)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("stems", nargs="*")
    a = ap.parse_args()
    for s in a.stems or ["fp_quantized_nax"]:
        regen(s, a.base)
