#!/usr/bin/env python3
"""Research-only: prove the flags-off kernel text equals BASE_SHA byte for byte.

The two Metal literals are now assembled from interpolated fragments. This
replicates Swift's multiline-literal indentation stripping and the OFF-path
interpolation, then diffs against the same literals at BASE_SHA.
"""
import difflib
import subprocess
import sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b"
PATH = "Sources/MLXFastModel/LagunaRuntimeModel.swift"


def literal_after(text, anchor, delim_indent=8):
    i = text.index(anchor)
    j = text.index('"""', i) + 3
    assert text[j] == "\n"
    k = text.index("\n" + " " * delim_indent + '"""', j)
    lines = []
    for line in text[j + 1:k].split("\n"):
        if line.strip() == "":
            lines.append("")
        else:
            assert line.startswith(" " * delim_indent), repr(line)
            lines.append(line[delim_indent:])
    return "\n".join(lines)


def fragment(text, name):
    i = text.index('private let %s = """\n' % name)
    j = text.index('"""', i) + 3
    k = text.index('\n"""', j)
    return text[j + 1:k]


base_src = subprocess.run(
    ["git", "show", "%s:%s" % (BASE, PATH)], capture_output=True, text=True, check=True
).stdout
cur_src = open(PATH).read()

K1_ANCHOR = 'name: "laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1"'
K3_ANCHOR = '"laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5"'

k1 = (
    literal_after(cur_src, K1_ANCHOR)
    .replace("\\(lagunaSharedSwiGLUQMVRows1Prologue)", "")
    .replace(
        "\\(lagunaSharedSwiGLUQMVRows1Body)",
        fragment(cur_src, "lagunaSharedQMVShippedBody"),
    )
    .replace(
        "\\(lagunaSharedSwiGLUQMVRows1Reduction)",
        fragment(cur_src, "lagunaSharedQMVScalarReduction"),
    )
)
failures = 0
for label, base, cur in (
    ("K1", literal_after(base_src, K1_ANCHOR), k1),
    (
        "K3",
        literal_after(base_src, K3_ANCHOR + ","),
        literal_after(cur_src, K3_ANCHOR + ","),
    ),
):
    if base == cur:
        print("%s: OFF path byte-identical to BASE_SHA (%d chars)" % (label, len(base)))
        continue
    failures += 1
    print("%s: DIFFERS" % label)
    diff = difflib.unified_diff(
        base.split("\n"), cur.split("\n"), "base", "cur", lineterm="", n=2
    )
    print("\n".join("    " + line for line in diff))
sys.exit(1 if failures else 0)
