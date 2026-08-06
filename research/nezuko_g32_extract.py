#!/usr/bin/env python3
"""Render the exact Metal text of two decode kernels from a LagunaRuntimeModel.swift.

Support tool for PR #72 (group-32 scale census / halving).  It never re-implements
the Swift string interpolation: it copies the relevant top-level declarations and
the kernel `source:` multi-line literal *verbatim* into a tiny Foundation-only Swift
renderer, compiles that with swiftc, and runs it.  Whatever the runtime would have
handed to `MLXFast.metalKernel` is exactly what lands in the emitted .metal file.

Usage:
    python3 research/nezuko_g32_extract.py --tag baseline --rev HEAD
    python3 research/nezuko_g32_extract.py --tag candidate --worktree
    python3 research/nezuko_g32_extract.py --preamble
Outputs land in /tmp/nezuko_g32/.
"""

import argparse
import os
import re
import subprocess
import sys

OUT_DIR = "/tmp/nezuko_g32"
SRC_PATH = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
UTILS_CPP = "Vendor/mlx-swift/Source/Cmlx/mlx-generated/utils.cpp"

# Top-level declarations the two kernel texts (and their headers) interpolate.
# Every one of these depends only on ProcessInfo/environment and literals, so the
# renderer compiles against Foundation alone.
DECLS = [
    "lagunaE4M3SignDomainCertified",
    "lagunaNvfp4ScaleFoldEnabled",
    "lagunaNvfp4NibbleSplit",
    "lagunaNvfp4ScaleCarry",
    "lagunaNvfp4QdotSeedElisionEnabled",
    "lagunaNvfp4ScaleDeferEnabled",
    "lagunaNvfp4RowScaleSuffix",
    "lagunaSharedSwiGLUQMVHeader",
    "lagunaDecodeRouterOrdinalHeader",
    "lagunaRouterTop8PrologueHeader",
    "lagunaRouterTop8PrecomputedPrelude",
    "lagunaScalePatchHeaderBytes",
]

KERNELS = {
    "r1": "lagunaRoutedSwiGLUQMVPackedTop8R1Kernel",
    "down": "lagunaRoutedDownReduceKernel",
    "sdr": "lagunaRoutedSharedDownResidualKernel",
}

# How each kernel's Metal text is assembled by MLXFast.metalKernel(header:source:).
HEADER_EXPR = {
    "r1": ('lagunaSharedSwiGLUQMVHeader + "\\n" + lagunaDecodeRouterOrdinalHeader '
           '+ "\\n" + lagunaRouterTop8PrologueHeader'),
    "down": "lagunaSharedSwiGLUQMVHeader",
    "sdr": "lagunaSharedSwiGLUQMVHeader",
}


def read_source(rev, worktree):
    if worktree:
        with open(SRC_PATH, "r") as f:
            return f.read()
    return subprocess.check_output(["git", "show", f"{rev}:{SRC_PATH}"], text=True)


def extract_decl(text, name):
    """Copy a top-level `let NAME ...` declaration verbatim.

    A top-level declaration in this file ends at the first following line that
    starts a new top-level construct, i.e. a non-blank line at column 0 that is
    not a continuation.  Tracked separately: multi-line string literals (\"\"\")
    and bracket depth, both of which legitimately contain column-0 text.
    """
    lines = text.split("\n")
    start = None
    pat = re.compile(r"^(private |internal |public )?let " + re.escape(name) + r"\b")
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i
            break
    if start is None:
        return None

    out = []
    in_multiline = False
    depth = 0
    for i in range(start, len(lines)):
        line = lines[i]
        if i > start and not in_multiline and depth == 0 and line[:1] not in ("", " ", "\t"):
            # A new column-0 construct begins here.
            break
        out.append(line)
        stripped = line.strip()
        if stripped.count('"""') % 2 == 1:
            in_multiline = not in_multiline
        if not in_multiline:
            depth += line.count("(") + line.count("{") + line.count("[")
            depth -= line.count(")") + line.count("}") + line.count("]")

    while out and not out[-1].strip():
        out.pop()
    decl = "\n".join(out)
    return re.sub(r"^(private|internal) ", "", decl)


def extract_kernel_source(text, name):
    """Copy the `source: \"\"\"...\"\"\"` literal of a metalKernel declaration verbatim."""
    lines = text.split("\n")
    start = None
    pat = re.compile(r"^(private |internal |public )?let " + re.escape(name) + r"\b")
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i
            break
    if start is None:
        raise SystemExit(f"kernel decl not found: {name}")

    open_idx = None
    for i in range(start, min(start + 40, len(lines))):
        if lines[i].strip() == 'source: """':
            open_idx = i
            break
    if open_idx is None:
        raise SystemExit(f"source literal not found for {name}")

    close_idx = None
    for i in range(open_idx + 1, len(lines)):
        if lines[i].strip().startswith('"""'):
            close_idx = i
            break
    if close_idx is None:
        raise SystemExit(f"unterminated source literal for {name}")

    body = lines[open_idx + 1:close_idx]
    indent = lines[close_idx][:len(lines[close_idx]) - len(lines[close_idx].lstrip())]
    return body, indent


def render(tag, text):
    decls = []
    for name in DECLS:
        d = extract_decl(text, name)
        if d is None:
            if name == "lagunaScalePatchHeaderBytes":
                continue  # absent in the baseline revision
            raise SystemExit(f"declaration not found: {name}")
        decls.append(d)

    parts = ["import Foundation", ""]
    parts.extend(decls)
    parts.append("")
    for key, kname in KERNELS.items():
        body, indent = extract_kernel_source(text, kname)
        parts.append(f'let source_{key} = """')
        parts.extend(body)
        parts.append(indent + '"""')
        parts.append("")
        parts.append(f"let header_{key} = {HEADER_EXPR[key]}")
        parts.append("")
    parts.append("let outDir = CommandLine.arguments[1]")
    parts.append('let tag = CommandLine.arguments[2]')
    for key in KERNELS:
        parts.append(
            f'try (header_{key} + "\\n// @@SOURCE@@\\n" + source_{key} + "\\n").write('
            f'toFile: outDir + "/" + tag + "_{key}.metaltext", atomically: true, encoding: .utf8)')
    parts.append('print("rendered \\(tag)")')

    swift_path = os.path.join(OUT_DIR, f"{tag}_render.swift")
    with open(swift_path, "w") as f:
        f.write("\n".join(parts))
    bin_path = os.path.join(OUT_DIR, f"{tag}_render")
    subprocess.check_call(["swiftc", "-O", swift_path, "-o", bin_path])
    subprocess.check_call([bin_path, OUT_DIR, tag])
    for key in KERNELS:
        p = os.path.join(OUT_DIR, f"{tag}_{key}.metaltext")
        print(f"  {p}: {os.path.getsize(p)} bytes")


def emit_preamble():
    with open(UTILS_CPP, "r") as f:
        cpp = f.read()
    start = cpp.index('R"preamble(') + len('R"preamble(')
    end = cpp.index(')preamble"')
    out = os.path.join(OUT_DIR, "preamble.metal")
    with open(out, "w") as f:
        f.write(cpp[start:end])
    print(f"  {out}: {os.path.getsize(out)} bytes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag")
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--worktree", action="store_true")
    ap.add_argument("--preamble", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.preamble:
        emit_preamble()
        return
    if not args.tag:
        sys.exit("--tag required")
    render(args.tag, read_source(args.rev, args.worktree))


if __name__ == "__main__":
    main()
