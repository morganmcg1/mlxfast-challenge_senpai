#!/usr/bin/env python3
"""Offline compile gate for the M5-only NAX Metal kernels.

The expert-aligned NAX gather-QMM is assembled at runtime by
jit_kernels.cpp:get_qmm_nax_kernel() and only ever compiled on a machine where
metal::is_nax_available() holds. On an M4 host nothing in `swift build`,
`swift test`, or `./benchmark.sh` ever compiles it, so a syntax or template
error in fp_quantized_nax.h / steel/gemm/nax.h ships undetected.

This reproduces that same concatenation from the mlx-generated raw-string twins
and hands it to `xcrun metal`, which is an offline AIR compiler and does not
need NAX hardware. It compiles the instantiations the Laguna prefill actually
dispatches, for both DARKBLOOM_STAGE2_GATHER arms, plus the non-NAX
fp_gather_qmm_rhs twin (which is the reverse blind spot: only a machine
WITHOUT NAX ever compiles that one at runtime).

    python3 research/nax-compile-gate.py            # all cases
    python3 research/nax-compile-gate.py --keep     # keep assembled sources

Exit status is non-zero if any case fails to compile.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "Vendor/mlx-swift/Source/Cmlx/mlx-generated")

# jit_kernels.cpp:get_qmm_nax_kernel() concatenation order.
PIECES = ["utils.cpp", "gemm_nax.cpp", "quantized_utils.cpp",
          "fp_quantized_nax.cpp"]

# quantized.cpp:1873-1894. Laguna prefill dispatches variant 5 geometry
# (bm=64 bn=64 bk=64 wm=4 wn=1) with static K/N per projection, egroups 256,
# and both wide-staging flags certified. Each entry is a host_name plus the
# fp_gather_qmm_rhs_expert_nax template argument list.
CASES = [
    ("gate_up_static", "bfloat16_t, 16, 4, 64, 64, 64, 4, 1, true, "
                       "2048, 1024, bfloat, 256, true, true"),
    ("down_static", "bfloat16_t, 16, 4, 64, 64, 64, 4, 1, true, "
                    "512, 2048, bfloat, 256, true, true"),
    # Uncertified weight bank: both wide flags off, dynamic shape.
    ("dynamic_scalar", "bfloat16_t, 16, 4, 64, 64, 64, 4, 1, true, "
                       "0, 0, bfloat, 256, false, false"),
    # Wide store certified but wide load refused (the per-bank asymmetry
    # darkbloom_stage_wide_load_ok can produce).
    ("gate_up_store_only", "bfloat16_t, 16, 4, 64, 64, 64, 4, 1, true, "
                           "2048, 1024, bfloat, 256, true, false"),
]

# The non-expert twin shares the loader, so it must still compile after any
# loader edit. It is built by get_gather_qmm_nax_kernel(), which injects no
# DARKBLOOM defines.
NONEXPERT = ("nonexpert", "fp_gather_qmm_rhs_nax",
             "bfloat16_t, 16, 4, 64, 64, 64, 4, 1, true")

# jit_kernels.cpp:get_gather_qmm_kernel() -- the NON-NAX gather-QMM. `swift
# build` does compile this one on an M4 (it is the only kernel this op can
# dispatch there), but not on a machine that has NAX, so the gate covers both
# directions. Geometry from quantized.cpp:2005-2006.
NONNAX_PIECES = ["utils.cpp", "quantized_utils.cpp", "gemm.cpp",
                 "fp_quantized.cpp"]
NONNAX_CASES = [
    ("nonnax", "fp_gather_qmm_rhs",
     "bfloat16_t, 16, 4, 16, 32, 32, 1, 2, true"),
]

# Negative control: the gate is only a gate if it rejects something. wn=4 gives
# SN = BN/WN = 16 -> TN = 1, and wm=4 gives SM = 16 -> TM = 1, so (TM, TN) =
# (1, 1) matches neither tile_matmad_nax branch. Before the static_assert in
# steel/gemm/nax.h this instantiation compiled cleanly and emitted no MMA at
# all, returning zeros. It must now fail to compile.
EXPECT_FAIL = [
    ("trap_tm1_tn1", "fp_gather_qmm_rhs_expert_nax",
     "bfloat16_t, 16, 4, 64, 64, 64, 4, 4, true, "
     "2048, 1024, bfloat, 256, true, true"),
]

RAW = re.compile(r'R"preamble\((.*)\)preamble"', re.DOTALL)


def preamble(name):
    with open(os.path.join(GEN, name)) as f:
        m = RAW.search(f.read())
    if not m:
        sys.exit(f"no R\"preamble(...)\" block in {name}")
    return m.group(1)


def assemble(pieces, define_pos, defines, func, targs, host_name):
    """Reproduce one jit_kernels.cpp concatenate(), defines at their real slot."""
    parts = [preamble(p) for p in pieces[:define_pos]]
    parts += defines
    parts += [preamble(p) for p in pieces[define_pos:]]
    parts.append(
        f'\ntemplate [[host_name("{host_name}")]] [[kernel]] '
        f"decltype({func}<{targs}>) {func}<{targs}>;\n")
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true",
                    help="write assembled sources next to this script")
    ap.add_argument("--only", help="run only cases whose tag contains this")
    args = ap.parse_args()

    expert_defines = {}
    for stage2 in (False, True):
        d = ["\n#define DARKBLOOM_STAGE2_GATHER 1\n"] if stage2 else []
        # Shipped defaults for the other two expert-kernel levers
        # (quantized.cpp:1580-1584, jit_kernels.cpp bsearch/swiglu defines).
        d += ["\n#define DARKBLOOM_SWIGLU_REGLOCAL 1\n",
              "\n#define DARKBLOOM_BSEARCH_HOIST 1\n"]
        expert_defines["stage2" if stage2 else "stock"] = d

    # (tag, pieces, define_pos, defines, func, targs, want_ok)
    jobs = []
    for tag, d in expert_defines.items():
        for name, targs in CASES:
            jobs.append((f"{tag}_{name}", PIECES, 1, d,
                         "fp_gather_qmm_rhs_expert_nax", targs, True))
    name, func, targs = NONEXPERT
    jobs.append((name, PIECES, 1, [], func, targs, True))
    for tag in ("stock", "stage2"):
        d = [] if tag == "stock" else ["\n#define DARKBLOOM_STAGE2_GATHER 1\n"]
        for name, func, targs in NONNAX_CASES:
            jobs.append((f"{tag}_{name}", NONNAX_PIECES, 3, d,
                         func, targs, True))
    for name, func, targs in EXPECT_FAIL:
        jobs.append((name, PIECES, 1, expert_defines["stage2"], func, targs,
                     False))
    if args.only:
        jobs = [j for j in jobs if args.only in j[0]]

    outdir = (os.path.dirname(os.path.abspath(__file__)) if args.keep
              else tempfile.mkdtemp(prefix="naxgate-"))
    failures = []
    for tag, pieces, define_pos, defines, func, targs, want_ok in jobs:
        src = os.path.join(outdir, f"naxgate_{tag}.metal")
        with open(src, "w") as f:
            f.write(assemble(pieces, define_pos, defines, func, targs,
                             f"gate_{tag}"))
        r = subprocess.run(
            ["xcrun", "metal", "-std=metal4.0", "-Wno-unused-function",
             "-c", src, "-o", os.path.join(outdir, f"naxgate_{tag}.air")],
            capture_output=True, text=True)
        ok = (r.returncode == 0) == want_ok
        note = "" if want_ok else "  (expected to be rejected)"
        print(f"{'PASS' if ok else 'FAIL'}  {tag}{note}")
        if not ok:
            failures.append(tag)
            sys.stdout.write(r.stderr if want_ok else "compiled but must not\n")
        elif not want_ok:
            for line in r.stderr.splitlines():
                if "error:" in line:
                    print(f"        {line.strip()}")

    print(f"\n{len(jobs) - len(failures)}/{len(jobs)} cases as expected"
          + (f"  (sources in {outdir})" if args.keep else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
