#!/usr/bin/env python3
"""Research-only: one-axis revert of the shipped depth-1 preload in routed gate/up.

Round-107 arm B.  The routed R1 gate/up kernel
(`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`,
`Sources/MLXFastModel/LagunaRuntimeModel.swift`) already ships the depth-1
software pipeline that PR #454 proposed: a prologue peel of K-block 0 and a
guarded next-block fetch inside the loop.  `DARKBLOOM_ROUTED_GATEUP_R1`
defaults ON, so that text is the scored decode path.

Round 99/100 (`research/artifacts/fern-r99`, `.../fern-r100`) measured the
shipped text against four *chunked-template* rewrites and found every one of
them ~1.8-2.0% faster at the faithful TG=2048 rung in the cache-defeated
regime -- but flat in staging depth (s1 == s2 == s4).  A flat dose-response
means the contrast is confounded: those variants change the preload depth AND
the surrounding spelling at the same time, so they cannot say which axis pays.

This script emits the missing one-axis arm.  `depth0_oneaxis` is the shipped
body with the cross-iteration preload removed and nothing else changed: same
loop bounds, same input-vector load, same `laguna_nvfp4_qdot_codes_16` calls,
same reduction and epilogue, same 64-thread geometry.  Block k's codes and
scale bytes are simply read at the top of iteration k instead of at the end of
iteration k-1.

Arms written to `research/artifacts/maple-alphonse-r107b/`:
  depth1_shipped   the scored text, re-emitted from the working tree (reference)
  noop_control     byte-identical copy of the reference (Rule 79 slot null)
  depth0_oneaxis   preload removed, one axis, bitwise-equivalent by construction
  fault_control    deliberately wrong up-scale index; proves the probe's
                   bitwise output gate can actually fail

Timed by `research/fern_r99_qmv_probe.swift` (Rule 58: reuse the instrument).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_FERN = pathlib.Path(__file__).resolve().parent / "fern_r99_qmv_variants.py"
_spec = importlib.util.spec_from_file_location("fern_r99_qmv_variants", _FERN)
fern = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fern)

OUT_DIR_NAME = "maple-alphonse-r107b"

# Depth-0 middle: identical to the shipped middle except that the codes and
# scale bytes for block k are loaded in iteration k rather than being latched by
# iteration k-1.  For block == 0 the addressing collapses to exactly the shipped
# prologue peel; for block > 0 it collapses to the shipped `next_block` fetch
# with `next_block` renamed `block`.  Hence bitwise identical output.
DEPTH0_MIDDLE = """

for (uint block = 0; block < input_width; block += block_width) {
    const device vec<bfloat, 4>* input_vectors =
        (const device vec<bfloat, 4>*) (
            input + block + lane * values_per_lane);
    for (uint i = 0; i < values_per_lane / 4; ++i) {
        const vec<bfloat, 4> values = input_vectors[i];
        input_values[4 * i] = values[0];
        input_values[4 * i + 1] = values[1];
        input_values[4 * i + 2] = values[2];
        input_values[4 * i + 3] = values[3];
    }

    const device uint8_t* cur_scales =
        row_scales + (block / block_width) * scale_kblock_bytes
        + sub * 2 * scale_row_bytes + (lane >> 1);
    bool patch_lane =
        expert == 0 && logical_row == 0 && lane == 1 && block == 0;
    const uint8_t cur_gate_sb = patch_lane ? packed_scales[0] : cur_scales[0];
    const uint8_t cur_up_sb =
        patch_lane ? packed_scales[1] : cur_scales[scale_row_bytes];
    const uint2 cur_gate_codes = *(const device uint2*)(
        expert_weight + gate_row * fused_row_bytes + block / 2 + lane * 8);
    const uint2 cur_up_codes = *(const device uint2*)(
        expert_weight + up_row * fused_row_bytes + block / 2 + lane * 8);

    gate_result += laguna_nvfp4_qdot_codes_16(
        cur_gate_codes, input_values,
        laguna_nvfp4_scale(cur_gate_sb));
    up_result += laguna_nvfp4_qdot_codes_16(
        cur_up_codes, input_values,
        laguna_nvfp4_scale(cur_up_sb));
}

"""

# Same as DEPTH0_MIDDLE but reads the gate scale byte for the up row.  Must
# produce a nonzero bitwise diff, otherwise the probe's equivalence gate is
# vacuous and no other arm's "diff 0" line means anything.
FAULT_MIDDLE = DEPTH0_MIDDLE.replace(
    "patch_lane ? packed_scales[1] : cur_scales[scale_row_bytes];",
    "patch_lane ? packed_scales[1] : cur_scales[0];",
)


def main() -> int:
    root = fern.repo_root()
    fern_dir = root / "research" / "artifacts" / "fern-r99"
    out_dir = root / "research" / "artifacts" / OUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    shared_header = (fern_dir / "shared_qmv_header.metal").read_text()
    router_prologue = (fern_dir / "router_top8_prologue.metal").read_text()

    work_lines = fern.read_source(root, None)
    ordinal_header = fern.literal_after(
        work_lines, "private let lagunaDecodeRouterOrdinalHeader"
    )
    prelude = fern.literal_after(
        work_lines, "private let lagunaRouterTop8PrecomputedPrelude"
    )
    header = shared_header + "\n" + ordinal_header + "\n" + router_prologue

    shipped = fern.resolve(fern.kernel_body(work_lines), prelude)
    head, tail = fern.split_body(shipped)

    assert "next_block" in shipped, "shipped body has no guarded next-block fetch"
    assert "next_block" not in head + DEPTH0_MIDDLE + tail, "revert left a preload"

    variants = {
        "depth1_shipped": shipped,
        "noop_control": shipped,
        "depth0_oneaxis": head + DEPTH0_MIDDLE + tail,
        "fault_control": head + FAULT_MIDDLE + tail,
    }

    for name, body in variants.items():
        msl = fern.PREAMBLE + header + "\n" + fern.SIGNATURE + body + "\n}\n"
        path = out_dir / f"{name}.metal"
        path.write_text(msl)
        print(f"{path.relative_to(root)}  {len(msl)} B  {msl.count(chr(10))} lines")

    # Drift gate: if the scored text moved since round 99, fern's recorded dose
    # ladder is not comparable with this run and must not be cited as a baseline.
    mine = (out_dir / "depth1_shipped.metal").read_text()
    theirs = (fern_dir / "depth1_shipped.metal").read_text()
    print(
        "reference-vs-fern-r99 drift: "
        + ("NONE (fern's r99/r100 ladder is comparable)" if mine == theirs
           else "PRESENT (do not cite fern's r99/r100 numbers as a baseline)")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
