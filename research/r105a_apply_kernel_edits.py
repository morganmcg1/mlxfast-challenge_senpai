#!/usr/bin/env python3
"""Apply the 105-A BN=128 kernel edits to both the .h and its generated twin.

The GPU runs Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp;
a header-only edit is inert. Every replacement below must land in both files
the same number of times or this script fails loudly.
"""
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h",
    ROOT / "Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp",
]

EDITS = []

# ---------------------------------------------------------------- 1. loader
EDITS.append((
    """  MLX_MTL_CONST bool kWideLoad8ShapeOk = kWidenShapeOk && (kSrcBytes == 8);
""",
    """  MLX_MTL_CONST bool kWideLoad8ShapeOk = kWidenShapeOk && (kSrcBytes == 8);
  // Two adjacent 16B device loads cover it instead (the BN = 128
  // expert-aligned geometry: n_reads 32, one packed byte each). Same
  // exactness class as the 16B form -- the same source bytes reach the same
  // sb[] slots in the same order -- and the host's 16B base certification
  // covers both halves, because the second half starts exactly 16B into the
  // same contiguous run the first half certified.
  MLX_MTL_CONST bool kWideLoad32ShapeOk = kWidenShapeOk && (kSrcBytes == 32);
""",
))

EDITS.append((
    """  struct alignas(8) WideSrc8 {
    uint8_t b[kSrcBytes];
  };
""",
    """  struct alignas(8) WideSrc8 {
    uint8_t b[kSrcBytes];
  };
  struct alignas(16) WideSrc16 {
    uint8_t b[16];
  };
""",
))

EDITS.append((
    """    const bool load_ok = wide_load &&
        ((kWideLoadShapeOk && ((src_byte_off() & 15) == 0)) ||
         (kWideLoad8ShapeOk && ((src_byte_off() & 7) == 0)));
""",
    """    const bool load_ok = wide_load &&
        ((kWideLoadShapeOk && ((src_byte_off() & 15) == 0)) ||
         (kWideLoad32ShapeOk && ((src_byte_off() & 15) == 0)) ||
         (kWideLoad8ShapeOk && ((src_byte_off() & 7) == 0)));
""",
))

EDITS.append((
    """    if constexpr (kWideLoad8ShapeOk) {
      if (load_ok) {
        WideSrc8 packed = *((const device WideSrc8*)src);
""",
    """    if constexpr (kWideLoad32ShapeOk) {
      if (load_ok) {
        const device WideSrc16* wsrc = (const device WideSrc16*)src;
        WideSrc16 lo = wsrc[0];
        WideSrc16 hi = wsrc[1];
        STEEL_PRAGMA_UNROLL
        for (short b = 0; b < 16; b++) {
          sb[b] = lo.b[b];
          sb[16 + b] = hi.b[b];
        }
        took_wide_load = true;
      }
    }
    if constexpr (kWideLoad8ShapeOk) {
      if (load_ok) {
        WideSrc8 packed = *((const device WideSrc8*)src);
""",
))

# ------------------------------------------------ 2. wide-load static guard
EDITS.append((
    """  constexpr int kWsElems = BN * BK_padded;
""",
    """  // #138 Finding D: widening a tile once silently flipped kSrcBytes 16 -> 32,
  // which statically disables the wide device load and degrades the weight
  // stage to kSrcBytes scalar byte loads per thread per k-iteration. The host
  // certification (darkbloom_stage_wide_load_ok) does not see that, so the
  // emitted kernel name still reads _wl_1. Fail the build instead.
  static_assert(
      !wide_load || loader_w_t::kWideLoadShapeOk ||
          loader_w_t::kWideLoad8ShapeOk || loader_w_t::kWideLoad32ShapeOk,
      "wide_load requested but this loader shape falls back to scalar "
      "per-byte device loads");

  constexpr int kWsElems = BN * BK_padded;
""",
))

# --------------------------------------------------- 3. swiglu, reg-local
EDITS.append((
    """  constexpr bool kSwigluRegLocal =
      (WN == 1) && (BN == 64) && ((BM / WM) == 16);
""",
    """  // BN is admitted in 64-column blocks rather than only at 64: the host pack
  // pairs weight row r with r + 32 inside each 64-row block, so a wider tile
  // simply holds BN / 64 independent gate/up blocks and the same in-lane
  // fragment pairing (j <-> j + 2) repeats once per block.
  constexpr bool kSwigluRegLocal =
      (WN == 1) && (BN % 64 == 0) && ((BM / WM) == 16);
""",
))

EDITS.append((
    """          STEEL_PRAGMA_UNROLL
          for (short jf = 0; jf < 2; ++jf) {
            STEEL_PRAGMA_UNROLL
            for (short ie = 0; ie < 2; ++ie) {
              const short row = fm + ie * 8;
              if (row < sgp_sm) {
                STEEL_PRAGMA_UNROLL
                for (short jj = 0; jj < 4; ++jj) {
                  const int col = jf * 16 + fn + jj;
                  const bfloat gate = static_cast<bfloat>(
                      Dtile.frag_at(0, jf)[ie * 4 + jj]);
                  const bfloat up = static_cast<bfloat>(
                      Dtile.frag_at(0, jf + 2)[ie * 4 + jj]);
""",
    """          STEEL_PRAGMA_UNROLL
          for (short blk = 0; blk < BN / 64; ++blk) {
          STEEL_PRAGMA_UNROLL
          for (short jf = 0; jf < 2; ++jf) {
            STEEL_PRAGMA_UNROLL
            for (short ie = 0; ie < 2; ++ie) {
              const short row = fm + ie * 8;
              if (row < sgp_sm) {
                STEEL_PRAGMA_UNROLL
                for (short jj = 0; jj < 4; ++jj) {
                  const int col = blk * 32 + jf * 16 + fn + jj;
                  const bfloat gate = static_cast<bfloat>(
                      Dtile.frag_at(0, blk * 4 + jf)[ie * 4 + jj]);
                  const bfloat up = static_cast<bfloat>(
                      Dtile.frag_at(0, blk * 4 + jf + 2)[ie * 4 + jj]);
""",
))

EDITS.append((
    """                }
              }
            }
          }
        }
        if constexpr (!kSwigluRegLocal) {
""",
    """                }
              }
            }
          }
          }
        }
        if constexpr (!kSwigluRegLocal) {
""",
))

# ------------------------------------------------------ 4. swiglu, staged
EDITS.append((
    """            const int row = linear / activated_cols;
            const int col = linear % activated_cols;
            const bfloat gate =
                gate_up_stage[(tm + row) * BN + col];
            const bfloat up =
                gate_up_stage[(tm + row) * BN + activated_cols + col];
""",
    """            const int row = linear / activated_cols;
            const int col = linear % activated_cols;
            // Gate/up partners are 32 weight rows apart inside each 64-row
            // block (host: preparePackedRoutedGateUpBank, pairRows = 32), not
            // activated_cols apart. Identical to `col` / `activated_cols + col`
            // when BN == 64; correct for any multiple of 64.
            // `linear % activated_cols` is a signed remainder, so the compiler
            // cannot prove col >= 0; spell the BN == 64 case out so it folds.
            const int blk = (BN == 64) ? 0 : (col >> 5);
            const int c = (BN == 64) ? col : (col & 31);
            const bfloat gate =
                gate_up_stage[(tm + row) * BN + blk * 64 + c];
            const bfloat up =
                gate_up_stage[(tm + row) * BN + blk * 64 + 32 + c];
""",
))


def main():
    failures = []
    for path in TARGETS:
        text = path.read_text()
        for i, (old, new) in enumerate(EDITS):
            n = text.count(old)
            if n != 1:
                failures.append(f"{path.name}: edit {i} matched {n} times")
                continue
            text = text.replace(old, new, 1)
        path.write_text(text)
    if failures:
        print("\n".join(failures))
        return 1
    print(f"applied {len(EDITS)} edits to {len(TARGETS)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
