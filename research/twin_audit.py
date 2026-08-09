#!/usr/bin/env python3
"""Section-aware staleness audit for every ``mlx-generated/*.cpp`` twin.

The MLX source generator does not copy one header into the ``R"preamble( ... )``
literal. It *recursively inlines* the header's include graph and separates each
inlined file with a banner:

    ///////////////////////////////////////////////////////////////////////////
    // Contents from "mlx/backend/metal/kernels/steel/gemm/nax.h"
    ///////////////////////////////////////////////////////////////////////////

So the single-header classifier in ``nax_twin_check.py`` is only valid for
self-contained headers such as ``fp_quantized_nax.h``. For ``gemm_nax`` the
header is 131 lines while the embedded block is ~1580: the rest comes from
seven other headers, and a stale copy of any one of them silently keeps an old
kernel on the GPU while every compile, link and static check passes.

This auditor splits the embedded block on those banners and diffs each section
against the on-disk header it names. Ignored, because the generator always
strips them: ``#include`` lines, ``#pragma once``, and ``// PRAGMA-VARIANT``
comment runs. Everything else counts as drift.

Usage:
    research/twin_audit.py                 # audit every mlx-generated/*.cpp
    research/twin_audit.py gemm_nax ...    # audit selected stems
"""

import collections
import difflib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CMLX = ROOT / "Vendor/mlx-swift/Source/Cmlx"
GEN_DIR = CMLX / "mlx-generated"
MLX_ROOT = CMLX / "mlx"

BANNER = re.compile(r'^// Contents from "(.+)"$')
ROOT_HDR = re.compile(r"^// Auto generated source for (.+)$")
RULE = re.compile(r"^/{40,}$")
COPYRIGHT = re.compile(r"\s*// Copyright\b")


def embedded_block(cpp_lines, stem):
    starts = [i for i, l in enumerate(cpp_lines) if 'R"preamble(' in l]
    ends = [i for i, l in enumerate(cpp_lines) if ')preamble";' in l]
    if not starts or not ends:
        raise SystemExit(f'{stem}: no R"preamble( ... )preamble" block')
    return cpp_lines[starts[0] + 1 : ends[0]]


def split_sections(block):
    """-> (root_header_or_None, [(header_path, body_lines), ...])"""
    root = None
    marks = []
    for i, l in enumerate(block):
        m = ROOT_HDR.match(l)
        if m and root is None:
            root = m.group(1)
        m = BANNER.match(l)
        if m:
            marks.append((i, m.group(1)))

    sections = []
    for n, (i, path) in enumerate(marks):
        # body starts after the banner's closing rule line
        s = i + 1
        while s < len(block) and RULE.match(block[s]):
            s += 1
        e = marks[n + 1][0] if n + 1 < len(marks) else len(block)
        # drop the opening rule line of the next banner / trailing rule
        while e > s and RULE.match(block[e - 1]):
            e -= 1
        sections.append((path, block[s:e]))
    return root, sections


def strip(lines):
    """Remove exactly what the generator is known to drop."""
    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        if re.match(r"\s*#(include|pragma once|line)\b", l):
            i += 1
            continue
        if "PRAGMA-VARIANT" in l and re.match(r"\s*//", l):
            while i < len(lines) and re.match(r"\s*//", lines[i]):
                i += 1
            continue
        out.append(l)
        i += 1
    return out


def trim(lines):
    a, b = 0, len(lines)
    while a < b and not lines[a].strip():
        a += 1
    while b > a and not lines[b - 1].strip():
        b -= 1
    return lines[a:b]


def resolve(header_path):
    """Map a banner path like mlx/backend/... to the vendored file."""
    if header_path.startswith("/"):
        return None  # Metal toolchain SDK header, not vendored
    p = MLX_ROOT / header_path
    return p if p.exists() else None


def code_only(lines):
    """Comment- and whitespace-insensitive view: what the compiler sees."""
    text = re.sub(r"/\*.*?\*/", "", "\n".join(lines), flags=re.S)
    out = []
    for l in text.splitlines():
        l = re.sub(r"//.*$", "", l).strip()
        if l:
            out.append(re.sub(r"\s+", " ", l))
    return out


def hunks(a, b, limit=8):
    diff = [
        l
        for l in difflib.unified_diff(a, b, lineterm="", n=0)
        if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))
    ]
    return len(diff), diff[:limit]


def audit(stem):
    gen = GEN_DIR / f"{stem}.cpp"
    block = embedded_block(gen.read_text().splitlines(), stem)
    root, sections = split_sections(block)

    # Hand-edited twins put shared #define defaults in the prologue ahead of the
    # first banner while the header carries them inside its own body. Fold the
    # prologue into the root header's section so the two are comparable.
    marks = [i for i, l in enumerate(block) if BANNER.match(l)]
    prologue = block[: marks[0]] if marks else []

    code_drift, reordered, comment_drift = [], [], []
    checked = 0
    skipped = []
    for path, body in sections:
        hdr = resolve(path)
        if hdr is None:
            skipped.append(path)
            continue
        checked += 1
        src = hdr.read_text().splitlines()
        if path == root:
            body = prologue + body
        raw_a = [l.rstrip() for l in strip(src) if l.strip() and not COPYRIGHT.match(l)]
        raw_b = [l.rstrip() for l in strip(body) if l.strip() and not COPYRIGHT.match(l)]
        if raw_a == raw_b:
            continue
        a, b = strip(code_only(src)), strip(code_only(body))
        if collections.Counter(a) != collections.Counter(b):
            code_drift.append((path, *hunks(a, b)))
        elif a != b:
            reordered.append(path)
        else:
            comment_drift.append(path)
    return {
        "stem": stem,
        "root": root,
        "sections": len(sections),
        "checked": checked,
        "skipped": skipped,
        "code_drift": code_drift,
        "reordered": reordered,
        "comment_drift": comment_drift,
    }


def main():
    stems = sys.argv[1:]
    if not stems:
        stems = sorted(p.stem for p in GEN_DIR.glob("*.cpp"))

    surface = set(json.loads((ROOT / "benchmark.json").read_text())["editablePaths"])

    results = []
    stale = soft = 0
    for stem in stems:
        r = audit(stem)
        rel = f"Vendor/mlx-swift/Source/Cmlx/mlx-generated/{stem}.cpp"
        r["editable"] = rel in surface
        results.append(r)
        stale += bool(r["code_drift"])
        soft += bool(r["reordered"] or r["comment_drift"])

    for r in results:
        tag = "EDITABLE" if r["editable"] else "readonly"
        head = (
            f"{r['stem']:26s} [{tag}] sections={r['sections']:2d} "
            f"checked={r['checked']:2d} skipped={len(r['skipped'])}"
        )
        if r["code_drift"]:
            print(f"STALE {head}")
        elif r["reordered"] or r["comment_drift"]:
            print(f"note  {head}")
        else:
            print(f"OK    {head}")
        for path, n, sample in r["code_drift"]:
            print(f"        CODE DRIFT {path}: {n} differing line(s)")
            for l in sample:
                print(f"          {l}")
        for path in r["reordered"]:
            print(f"        same code lines, different order: {path}")
        for path in r["comment_drift"]:
            print(f"        comment/formatting-only drift: {path}")

    print()
    print(
        f"TWIN AUDIT: {stale}/{len(results)} twin(s) with code drift, "
        f"{soft} with reordering or comment-only drift"
    )
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
