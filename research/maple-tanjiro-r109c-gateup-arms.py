#!/usr/bin/env python3
"""R109-C stage 0(b): emit the three ceiling-probe arms for the routed gate/up QMV.

Arm A is the verbatim shipped `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
text, prologue included.  Arm B deletes the whole
`laguna_router_top8_extract_round` prologue and reads the winning expert for the
threadgroup's slot straight out of the probe's router-key buffer at word
`256 + expert_slot`, where `research/maple_tanjiro_r109c_gateup_probe.swift`
stores the top-8 in goodness order.

A - B is therefore the in-kernel ceiling for the real candidate (gate/up reading
the tournament's `inds`), measured with *no* new cross-kernel dependency: the
serialization price of that dependency is a separate end-to-end question.

Both arms touch the same eight expert regions in the same slot order, so the
probe's bitwise output gate is a genuine equivalence check.

Nothing under `Sources/` is read for anything but text: the resolved kernel is
compiled outside the tree.

usage: maple-tanjiro-r109c-gateup-arms.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "fern_r99_qmv_variants", HERE / "fern_r99_qmv_variants.py"
)
fq = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fq)

PROLOGUE_TOKEN = "\\(lagunaRouterTop8PrecomputedPrelude)\nuint expert = top8_winner;"
DIRECT_READ = "uint expert = router_keys[256u + expert_slot];"

# Arm C keeps the selection in-kernel but runs it in one simdgroup instead of
# two.  Both simdgroups of a 64-thread threadgroup share `expert_slot` and read
# the same `router_keys`, so the broadcast value is the one simdgroup 1 would
# have computed itself; the arm is bit-exact by construction and needs no new
# buffer, no producer change, and no cross-kernel dependency.
SG0_BROADCAST = "\n".join(
    [
        "threadgroup uint tg_top8_winner;",
        "if (simd_group == 0u) {",
        "\\(lagunaRouterTop8PrecomputedPrelude)",
        "    if (lane == 0u) { tg_top8_winner = top8_winner; }",
        "}",
        "threadgroup_barrier(mem_flags::mem_threadgroup);",
        "uint expert = tg_top8_winner;",
    ]
)

OUT = HERE / "artifacts" / "maple-tanjiro-r109c"


def main() -> int:
    root = fq.repo_root()
    lines = fq.read_source(root, None)
    prelude = fq.literal_after(
        lines, "private let lagunaRouterTop8PrecomputedPrelude"
    )
    header = "\n".join(
        [
            (HERE / "artifacts" / "fern-r99" / "shared_qmv_header.metal").read_text(),
            fq.literal_after(lines, "private let lagunaDecodeRouterOrdinalHeader"),
            (HERE / "artifacts" / "fern-r99" / "router_top8_prologue.metal").read_text(),
        ]
    )
    raw = fq.kernel_body(lines)
    assert raw.count(PROLOGUE_TOKEN) == 1, "prologue anchor moved"

    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    arms = {
        "A_base": raw,
        "B_inds": raw.replace(PROLOGUE_TOKEN, DIRECT_READ),
        "C_sg0": raw.replace(PROLOGUE_TOKEN, SG0_BROADCAST),
    }
    for name, body in arms.items():
        text = (
            fq.PREAMBLE
            + header
            + "\n"
            + fq.SIGNATURE
            + fq.resolve(body, prelude)
            + "\n}\n"
        )
        path = OUT / f"{name}.metal"
        path.write_text(text)
        print(
            f"{path.relative_to(root)}  {len(text)} B  "
            f"{text.count(chr(10)) + 1} lines  base={sha}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
