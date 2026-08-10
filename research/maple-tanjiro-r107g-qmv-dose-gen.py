#!/usr/bin/env python3
"""R107-G family D (T2c routed gate/up QMV): emit instruction-dosed MSL arms.

Reuses `research/fern_r99_qmv_variants.py` for literal extraction and
interpolation resolution (the routed R1 literal carries Swift interpolation, so
a textual extractor cannot read it).  Nothing in `Sources/` is touched: the
kernel text is resolved into a standalone `.metal` file and compiled outside
the tree, which is what the R107-G charge requires for the four reserved line
ranges (`:7892-8065` is edward's).

Dose design
-----------
`DOSE` rounds of 8 independent fp32 `fma` are inserted into the main K-block
loop of `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`, seeded from
that iteration's live `input_values` registers so the chain cannot be hoisted,
with 8 accumulators so the dose measures *issue slots* and not fma latency.

The chain is sunk through a comparison against an unreachable value
(`dzs == 1e37f`).  The compiler cannot prove the branch is never taken, so the
arithmetic must be issued, but the branch is uniform-false at run time and the
kernel's stores are therefore **bit-identical to the base by construction** --
which fern's probe then verifies independently with its bitwise output gate.

The sink costs one compare + one uniform branch per iteration.  That cost is
*identical* in every dosed arm, so it cancels exactly in the 4 -> 8 -> 16 dose
slope.  Dose 0 is a verbatim copy of the shipped text and is used as the A/B
null control, not as a slope point.

usage: maple-tanjiro-r107g-qmv-dose-gen.py [DOSE ...]
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "fern_r99_qmv_variants", HERE / "fern_r99_qmv_variants.py"
)
fq = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fq)

# Anchor: the two shipped accumulate statements at the bottom of the K-block
# loop.  The dose lands immediately before them, after `input_values` is filled.
ANCHOR = "    gate_result += laguna_nvfp4_qdot_codes_16("


def dose_block(dose: int) -> str:
    body = "\n".join(
        f"            dz{i} = metal::fma(dz{i}, 1.0000001f, 1e-6f);" for i in range(8)
    )
    seeds = "\n".join(
        f"        float dz{i} = input_values[{i}];" for i in range(8)
    )
    return f"""    // [R107-G dose={dose}] {dose} rounds x 8 independent fp32 fma, seeded from
    // this iteration's live input_values, sunk through an unreachable compare.
    {{
{seeds}
        for (int dd = 0; dd < {dose}; ++dd) {{
{body}
        }}
        float dzs = ((dz0 + dz1) + (dz2 + dz3)) + ((dz4 + dz5) + (dz6 + dz7));
        if (dzs == 1e37f) {{ gate_result += 1.0f; }}
    }}
"""


def main() -> int:
    doses = [int(a) for a in sys.argv[1:]] or [0, 4, 8, 16]
    root = fq.repo_root()
    fern_dir = root / "research" / "artifacts" / "fern-r99"
    out_dir = root / "research" / "artifacts" / "maple-tanjiro-r107g"
    out_dir.mkdir(parents=True, exist_ok=True)

    shared_header = (fern_dir / "shared_qmv_header.metal").read_text()
    router_prologue = (fern_dir / "router_top8_prologue.metal").read_text()
    work_lines = fq.read_source(root, None)
    ordinal_header = fq.literal_after(
        work_lines, "private let lagunaDecodeRouterOrdinalHeader"
    )
    prelude = fq.literal_after(
        work_lines, "private let lagunaRouterTop8PrecomputedPrelude"
    )
    header = shared_header + "\n" + ordinal_header + "\n" + router_prologue
    shipped = fq.resolve(fq.kernel_body(work_lines), prelude)

    assert shipped.count(ANCHOR) == 1, (
        f"dose anchor appears {shipped.count(ANCHOR)}x, expected once -- "
        "the shipped K-loop text moved; re-derive before dosing"
    )

    rev = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip()

    for d in doses:
        body = shipped if d == 0 else shipped.replace(ANCHOR, dose_block(d) + ANCHOR)
        msl = fq.PREAMBLE + header + "\n" + fq.SIGNATURE + body + "\n}\n"
        path = out_dir / f"qmv_dose{d}.metal"
        path.write_text(msl)
        print(
            f"{path.relative_to(root)}  {len(msl)} B  {msl.count(chr(10))} lines"
            f"  dose={d}  extra_fma_per_thread={d * 8 * 4}  head={rev}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
