#!/usr/bin/env python3
"""Make the generalized reg-local swiglu epilogue constant-fold at BN == 64.

`blk` is short-typed, so `blk * 4 + jf` survives front-end IR as a
sign-extension roundtrip that the optimizer cannot fold, and the BN == 64
kernel stops being byte-identical to the pre-generalization one. Hoisting the
blk terms behind a `kNBlk == 1` ternary restores exact inertness.

Applies the identical edit to the header and the mlx-generated twin.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h",
    ROOT / "Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp",
]

EDITS = [
    (
        """          STEEL_PRAGMA_UNROLL
          for (short blk = 0; blk < BN / 64; ++blk) {
          STEEL_PRAGMA_UNROLL
          for (short jf = 0; jf < 2; ++jf) {""",
        """          constexpr short kNBlk = BN / 64;
          STEEL_PRAGMA_UNROLL
          for (short blk = 0; blk < kNBlk; ++blk) {
          // A short-typed `blk` term survives front-end IR as a
          // sign-extension roundtrip, which would make BN == 64 codegen
          // differ from the pre-generalization kernel for no semantic reason.
          const short fbase = (kNBlk == 1) ? short(0) : short(blk * 4);
          const int cbase = (kNBlk == 1) ? 0 : int(blk) * 32;
          STEEL_PRAGMA_UNROLL
          for (short jf = 0; jf < 2; ++jf) {""",
    ),
    (
        """                  const int col = blk * 32 + jf * 16 + fn + jj;
                  const bfloat gate = static_cast<bfloat>(
                      Dtile.frag_at(0, blk * 4 + jf)[ie * 4 + jj]);
                  const bfloat up = static_cast<bfloat>(
                      Dtile.frag_at(0, blk * 4 + jf + 2)[ie * 4 + jj]);""",
        """                  const int col = cbase + jf * 16 + fn + jj;
                  const bfloat gate = static_cast<bfloat>(
                      Dtile.frag_at(0, fbase + jf)[ie * 4 + jj]);
                  const bfloat up = static_cast<bfloat>(
                      Dtile.frag_at(0, fbase + jf + 2)[ie * 4 + jj]);""",
    ),
]


def main() -> int:
    for path in TARGETS:
        text = path.read_text()
        for old, new in EDITS:
            n = text.count(old)
            if n != 1:
                print(f"ABORT {path.name}: pattern matched {n} times", file=sys.stderr)
                return 1
            text = text.replace(old, new)
        path.write_text(text)
        print(f"applied {len(EDITS)} edits to {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
