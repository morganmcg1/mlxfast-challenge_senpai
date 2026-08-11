#!/usr/bin/env python3
"""Apply the R110-B register-prefetch (pf) transform to the vendored MLX
sources, keeping each kernel header byte-consistent with its mlx-generated
JIT twin. Idempotent: re-running is a no-op."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CMLX = ROOT / "Vendor/mlx-swift/Source/Cmlx"

STEEL_ANCHOR = """  /* Load from device memory into threadgroup memory - without bound checking */
  METAL_FUNC void load_unsafe() const {
    STEEL_PRAGMA_UNROLL
    for (short i = 0; i < BROWS; i += TROWS) {
      *((threadgroup ReadVector*)(&dst[i * dst_ld])) =
          *((const device ReadVector*)(&src[i * src_ld]));
    }
  }
"""

STEEL_ADD = """
  /* Register staging for gemm_loop_aligned_pf: prefetch() issues only the
   * device reads, stage_regs() only the threadgroup stores. Together they move
   * exactly the bytes load_unsafe() would have moved, to the same addresses. */
  struct RegTile {
    ReadVector v[(BROWS + TROWS - 1) / TROWS];
  };

  METAL_FUNC void prefetch(thread RegTile& r) const {
    STEEL_PRAGMA_UNROLL
    for (short i = 0; i < BROWS; i += TROWS) {
      r.v[i / TROWS] = *((const device ReadVector*)(&src[i * src_ld]));
    }
  }

  METAL_FUNC void stage_regs(const thread RegTile& r) const {
    STEEL_PRAGMA_UNROLL
    for (short i = 0; i < BROWS; i += TROWS) {
      *((threadgroup ReadVector*)(&dst[i * dst_ld])) = r.v[i / TROWS];
    }
  }
"""

QUANT_ANCHOR = """  void load_unsafe() const {
    if (BCOLS_PACKED * BROWS < tgp_size && bi >= BROWS) {
      return;
    }

    stage();
  }
"""

QUANT_ADD = """
  // Register staging for gemm_loop_aligned_pf. prefetch() captures the same
  // packed codes and scale byte stage() would have read; stage_regs() feeds
  // them to the same decode. Split, the values and destinations are identical.
  struct RegTile {
    uint32_t c[fp4nv_fast ? (n_reads / 4) : 1];
    uint8_t b[fp4nv_fast ? 1 : n_reads];
    uint8_t s;
  };

  void prefetch(thread RegTile& r) const {
    if (BCOLS_PACKED * BROWS < tgp_size && bi >= BROWS) {
      return;
    }
    if constexpr (fp4nv_fast) {
      for (int i = 0; i < n_reads / 4; i++) {
        r.c[i] = fp4nv_pack4(src + i * 4);
      }
    } else {
      for (int i = 0; i < n_reads; i++) {
        r.b[i] = src[i * bytes_per_pack];
      }
    }
    r.s = *scales;
  }

  void stage_regs(const thread RegTile& r) const {
    if (BCOLS_PACKED * BROWS < tgp_size && bi >= BROWS) {
      return;
    }
    if constexpr (fp4nv_fast) {
      const float scale = fp4nv_scale_x16384(r.s);
      for (int i = 0; i < n_reads / 4; i++) {
        T vals[8];
        fp4nv_decode8<T>(r.c[i], scale, vals);
        for (int j = 0; j < 8; j++) {
          dst[i * 8 + j] = vals[j];
        }
      }
    } else {
      T scale = dequantize_scale<T, group_size>(r.s);
      for (int i = 0; i < n_reads; i++) {
        dequantize<T, bits>(r.b[i], scale, dst + i * pack_factor);
      }
    }
  }
"""

UTILS_ANCHOR = """METAL_FUNC void gemm_loop_aligned(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  for (int k = 0; k < k_iterations; k++) {
    threadgroup_barrier(mem_flags::mem_threadgroup);

    // Load elements into threadgroup memory
    loader_a.load_unsafe();
    loader_b.load_unsafe();

    threadgroup_barrier(mem_flags::mem_threadgroup);

    // Multiply and accumulate threadgroup elements
    mma_op.mma(As, Bs);

    // Prepare for next iteration
    loader_a.next();
    loader_b.next();
  }
}
"""

UTILS_ADD = """
// Register-prefetched form of gemm_loop_aligned. The device reads for K tile k
// are issued before the RAW barrier and the mma for tile k-1, so their latency
// overlaps that mma. Staging arrays, barrier count and the order of the K
// reduction are unchanged, so the accumulator sees the identical sequence.
template <typename T, typename mma_t, typename loader_a_t, typename loader_b_t>
METAL_FUNC void gemm_loop_aligned_pf(
    threadgroup T* As,
    threadgroup T* Bs,
    thread mma_t& mma_op,
    thread loader_a_t& loader_a,
    thread loader_b_t& loader_b,
    const int k_iterations) {
  if (k_iterations <= 0) {
    return;
  }

  typename loader_a_t::RegTile ra;
  typename loader_b_t::RegTile rb;

  loader_a.prefetch(ra);
  loader_b.prefetch(rb);
  loader_a.next();
  loader_b.next();

  for (int k = 1; k < k_iterations; k++) {
    threadgroup_barrier(mem_flags::mem_threadgroup);

    loader_a.stage_regs(ra);
    loader_b.stage_regs(rb);
    loader_a.prefetch(ra);
    loader_b.prefetch(rb);
    loader_a.next();
    loader_b.next();

    threadgroup_barrier(mem_flags::mem_threadgroup);

    mma_op.mma(As, Bs);
  }

  threadgroup_barrier(mem_flags::mem_threadgroup);

  loader_a.stage_regs(ra);
  loader_b.stage_regs(rb);

  threadgroup_barrier(mem_flags::mem_threadgroup);

  mma_op.mma(As, Bs);
}
"""

CALL_OLD = "gemm_loop_aligned(Xs, Ws, mma_op, loader_x, loader_w, K_it);"
CALL_NEW = "gemm_loop_aligned_pf(Xs, Ws, mma_op, loader_x, loader_w, K_it);"

INSERTIONS = [
    ("mlx/mlx/backend/metal/kernels/steel/gemm/loader.h", STEEL_ANCHOR, STEEL_ADD),
    ("mlx-generated/gemm.cpp", STEEL_ANCHOR, STEEL_ADD),
    ("mlx/mlx/backend/metal/kernels/fp_quantized.h", QUANT_ANCHOR, QUANT_ADD),
    ("mlx-generated/fp_quantized.cpp", QUANT_ANCHOR, QUANT_ADD),
    ("mlx/mlx/backend/metal/kernels/quantized_utils.h", UTILS_ANCHOR, UTILS_ADD),
    ("mlx-generated/quantized_utils.cpp", UTILS_ANCHOR, UTILS_ADD),
]

CALL_SITES = [
    "mlx/mlx/backend/metal/kernels/fp_quantized.h",
    "mlx-generated/fp_quantized.cpp",
]


def main() -> int:
    for rel, anchor, addition in INSERTIONS:
        path = CMLX / rel
        text = path.read_text()
        if addition in text:
            print(f"skip (already applied) {rel}")
            continue
        if text.count(anchor) != 1:
            print(f"ERROR anchor count {text.count(anchor)} in {rel}")
            return 1
        path.write_text(text.replace(anchor, anchor + addition))
        print(f"inserted {rel}")

    for rel in CALL_SITES:
        path = CMLX / rel
        text = path.read_text()
        n = text.count(CALL_OLD)
        if n == 0 and CALL_NEW in text:
            print(f"skip (already applied) {rel} call sites")
            continue
        if n != 2:
            print(f"ERROR call-site count {n} in {rel}")
            return 1
        path.write_text(text.replace(CALL_OLD, CALL_NEW))
        print(f"rewired 2 call sites {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
