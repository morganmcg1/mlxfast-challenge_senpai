#!/usr/bin/env python3
"""Research-only: emit fully resolved MSL variants of the routed gate/up QMV.

The routed R1 kernel literal in `LagunaRuntimeModel.swift` carries Swift string
interpolation, so nezuko's textual extractor (which asserts the literal has no
`\\(`) cannot read it.  This script resolves the four interpolations, prepends
the compiler-dumped `lagunaSharedSwiGLUQMVHeader` (see
`research/fern_r99_dump_header.sh`) and the two router headers, and writes a
`.metal` file per staging-depth variant.

Dose axis: bytes of weight codes staged per lane before any math.
  depth1_shipped  rolling depth-1 prefetch, the base text            (16 B + 16 B)
  tmpl_s1         chunked template, stage 1 / compute 1, 4 chunks    (16 B)
  tmpl_s2         chunked template, stage 2 / compute 2, 2 chunks    (32 B)
  tmpl_s4         chunked template, stage 4 / compute 4, 1 chunk     (64 B)
  stage4_cand     the branch's rung-1 text                           (64 B)

`tmpl_s4` and `stage4_cand` are the same dose by two spellings; their gap
measures template fidelity, not ILP.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

KERNEL = "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2"
RUNTIME = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
SCALE_PATCH_HEADER_BYTES = 128  # Sources/MLXFastModel/LagunaRuntimeWeights.swift:985

# The two bfloat math overloads MLX's own preamble supplies through
# `bf16_math.h`; the epilogue's `metal::exp(metal::abs(gate))` is ambiguous
# without them. Same spelling and same rounding path as
# `instantiate_metal_math_funcs(bfloat16_t, bfloat16_t, float,
# __METAL_MAYBE_FAST_MATH__)`.
PREAMBLE = """#include <metal_stdlib>
#include <metal_simdgroup>
using namespace metal;
typedef bfloat bfloat16_t;

namespace metal {
METAL_FUNC bfloat16_t abs(bfloat16_t x) {
  return static_cast<bfloat16_t>(
      __metal_fabs(static_cast<float>(x), __METAL_MAYBE_FAST_MATH__));
}
METAL_FUNC bfloat16_t exp(bfloat16_t x) {
  return static_cast<bfloat16_t>(
      __metal_exp(static_cast<float>(x), __METAL_MAYBE_FAST_MATH__));
}
}

"""

SIGNATURE = f"""[[kernel]] void custom_kernel_{KERNEL}(
  const device bfloat16_t* input [[buffer(0)]],
  const device uint32_t* fused_weight [[buffer(1)]],
  const device uint8_t* packed_scales [[buffer(2)]],
  const device uint32_t* router_keys [[buffer(3)]],
  device bfloat16_t* activated [[buffer(4)]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {{
"""


def repo_root() -> pathlib.Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=pathlib.Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    )
    return pathlib.Path(out.stdout.strip())


def read_source(root: pathlib.Path, rev: str | None) -> list[str]:
    if rev is None:
        return (root / RUNTIME).read_text().splitlines()
    out = subprocess.run(
        ["git", "show", f"{rev}:{RUNTIME}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.splitlines()


def literal_after(lines: list[str], anchor: str) -> str:
    """Return the triple-quoted literal opened at or after `anchor`."""
    start = next(i for i, l in enumerate(lines) if anchor in l)
    open_i = next(
        i for i in range(start, len(lines)) if lines[i].strip().endswith('"""')
    )
    close_i = next(
        i for i in range(open_i + 1, len(lines)) if lines[i].strip() in ('"""', '""",')
    )
    return "\n".join(lines[open_i + 1 : close_i])


def kernel_body(lines: list[str]) -> str:
    return literal_after(lines, f'name: "{KERNEL}"')


def resolve(text: str, prelude: str) -> str:
    text = text.replace(
        "\\(lagunaScalePatchHeaderBytes)", str(SCALE_PATCH_HEADER_BYTES)
    )
    text = text.replace("\\(lagunaRouterTop8PrecomputedPrelude)", prelude)
    text = text.replace("\\(lagunaNvfp4RowScaleSuffix)", " * 4194304.0f")
    assert "\\(" not in text, "unresolved interpolation remains"
    return text


PROLOGUE_END = "thread float input_values[values_per_lane];"
EPILOGUE_START = "gate_result = simd_sum(gate_result);"


def split_body(body: str) -> tuple[str, str]:
    head, _, rest = body.partition(PROLOGUE_END)
    mid, sep, tail = rest.partition(EPILOGUE_START)
    assert sep, "epilogue anchor missing"
    return head + PROLOGUE_END, sep + tail


def staged_middle(depth: int) -> str:
    return f"""
constexpr uint k_blocks = input_width / block_width;
constexpr uint stage_depth = {depth};
constexpr uint chunks = k_blocks / stage_depth;
uint2 gate_codes[stage_depth];
uint2 up_codes[stage_depth];
uint8_t gate_sb[stage_depth];
uint8_t up_sb[stage_depth];
const device uint8_t* gate_base =
    expert_weight + gate_row * fused_row_bytes + lane * 8;
const device uint8_t* up_base =
    expert_weight + up_row * fused_row_bytes + lane * 8;
const device uint8_t* scale_base =
    row_scales + sub * 2 * scale_row_bytes + (lane >> 1);
bool patch_lane = expert == 0 && logical_row == 0 && lane == 1;

#pragma clang loop unroll(full)
for (uint c = 0; c < chunks; ++c) {{
#pragma clang loop unroll(full)
    for (uint s = 0; s < stage_depth; ++s) {{
        const uint k = c * stage_depth + s;
        const device uint8_t* k_scales = scale_base + k * scale_kblock_bytes;
        bool patch = patch_lane && k == 0;
        gate_sb[s] = patch ? packed_scales[0] : k_scales[0];
        up_sb[s] = patch ? packed_scales[1] : k_scales[scale_row_bytes];
        gate_codes[s] = *(const device uint2*)(
            gate_base + k * (block_width / 2));
        up_codes[s] = *(const device uint2*)(
            up_base + k * (block_width / 2));
    }}
#pragma clang loop unroll(full)
    for (uint s = 0; s < stage_depth; ++s) {{
        const uint k = c * stage_depth + s;
        const device vec<bfloat, 4>* input_vectors =
            (const device vec<bfloat, 4>*) (
                input + k * block_width + lane * values_per_lane);
        for (uint i = 0; i < values_per_lane / 4; ++i) {{
            const vec<bfloat, 4> values = input_vectors[i];
            input_values[4 * i] = values[0];
            input_values[4 * i + 1] = values[1];
            input_values[4 * i + 2] = values[2];
            input_values[4 * i + 3] = values[3];
        }}

        gate_result += laguna_nvfp4_qdot_codes_16(
            gate_codes[s], input_values,
            laguna_nvfp4_scale(gate_sb[s]));
        up_result += laguna_nvfp4_qdot_codes_16(
            up_codes[s], input_values,
            laguna_nvfp4_scale(up_sb[s]));
    }}
}}

"""


def main() -> int:
    root = repo_root()
    base_rev = sys.argv[1] if len(sys.argv) > 1 else "HEAD~0"
    out_dir = root / "research" / "artifacts" / "fern-r99"
    out_dir.mkdir(parents=True, exist_ok=True)

    shared_header = (out_dir / "shared_qmv_header.metal").read_text()
    router_prologue = (out_dir / "router_top8_prologue.metal").read_text()

    work_lines = read_source(root, None)
    base_lines = read_source(root, base_rev)
    ordinal_header = literal_after(
        work_lines, "private let lagunaDecodeRouterOrdinalHeader"
    )
    prelude = literal_after(
        work_lines, "private let lagunaRouterTop8PrecomputedPrelude"
    )

    header = shared_header + "\n" + ordinal_header + "\n" + router_prologue

    shipped = resolve(kernel_body(base_lines), prelude)
    candidate = resolve(kernel_body(work_lines), prelude)
    head, tail = split_body(shipped)

    variants = {
        "depth1_shipped": shipped,
        "tmpl_s1": head + staged_middle(1) + tail,
        "tmpl_s2": head + staged_middle(2) + tail,
        "tmpl_s4": head + staged_middle(4) + tail,
        "stage4_cand": candidate,
    }

    for name, body in variants.items():
        msl = PREAMBLE + header + "\n" + SIGNATURE + body + "\n}\n"
        path = out_dir / f"{name}.metal"
        path.write_text(msl)
        print(f"{path.relative_to(root)}  {len(msl)} B  {msl.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
