"""Render a standalone .metal probe from a JIT kernel literal in the runtime.

usage: python3 render.py <git-ref> <swift-identifier> <out.metal>
   eg: python3 render.py HEAD lagunaSlidingFusedAttentionKernel probe_orig.metal

MLX's `MLXFast.metalKernel` stores the kernel body without a signature and
prepends a generated one at JIT time. This script pastes the literal's `header`
and `source` around the fixed signature the probe harness binds, so the probe
compiles the same text the scored runtime compiles.
"""
import subprocess
import sys

REPO = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                      capture_output=True, text=True,
                      check=True).stdout.strip()
RUNTIME = "Sources/MLXFastModel/LagunaRuntimeModel.swift"

# Must match the buffer order `encode()` in main.swift binds.
SIGNATURE = """[[kernel]] void probe(
    const device bfloat* raw_queries [[buffer(0)]],
    const device bfloat* raw_keys [[buffer(1)]],
    const device bfloat* raw_values [[buffer(2)]],
    const device bfloat* query_weight [[buffer(3)]],
    const device bfloat* key_weight [[buffer(4)]],
    const device float* angles [[buffer(5)]],
    const device bfloat* k_cache [[buffer(6)]],
    const device bfloat* v_cache [[buffer(7)]],
    const device uint* params [[buffer(8)]],
    const device float* scale_arr [[buffer(9)]],
    device bfloat* attended [[buffer(10)]],
    uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],
    uint3 thread_position_in_grid [[thread_position_in_grid]],
    uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
    uint thread_index_in_simdgroup [[thread_index_in_simdgroup]])"""

ref, identifier, out = sys.argv[1], sys.argv[2], sys.argv[3]

text = subprocess.run(
    ["git", "-C", REPO, "show", "%s:%s" % (ref, RUNTIME)],
    capture_output=True, text=True, check=True).stdout

literal = text.split(
    "let %s = MLXFast.metalKernel(" % identifier, 1)[1]
source, rest = literal.split('    source: """\n', 1)[1].split(
    '\n        """,\n    header: """\n', 1)
# Swift string literals escape backslashes; Metal macro continuations need the
# single-backslash form the compiler actually sees.
header = rest.split('\n        """,\n    ensureRowContiguous', 1)[0].replace(
    "\\\\", "\\")

rendered = "\n".join([
    "#include <metal_stdlib>",
    "using namespace metal;",
    header,
    "",
    SIGNATURE + " {",
    source,
    "}",
    "",
])
open(out, "w").write(rendered)
print("%s <- %s:%s (%d bytes)" % (out, ref, identifier, len(rendered)))
