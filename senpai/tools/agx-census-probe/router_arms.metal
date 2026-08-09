// S4-a census arms for Lever 2 (the router-tournament instruction diet).
// Research only. This file is a fragment: run_s4a.sh prepends metal::utils()
// and lagunaDecodeRouterOrdinalHeader so every arm compiles in exactly the
// translation unit MLX would have compiled, with the exact generated signature
// of the scored decode router kernel.
//
// MOCK NOTICE. None of the r_* arms below is a correct top-8 router. They are
// instruction-budget probes that reuse the real comparator body verbatim. A
// real Lever 2 implementation must preserve laguna_router_ordinal_before
// verbatim and must independently pass research/maple_fern_pr82_oracle.sh
// (5,320 winner pairs, 0 diffs).

#define RSIG(name)                                                        \
  [[kernel]] void name(                                                   \
      const device bfloat16_t* logits [[buffer(0)]],                      \
      const device float* correction_bias [[buffer(1)]],                  \
      device uint32_t* router_indices [[buffer(2)]],                      \
      device float* router_scores [[buffer(3)]],                          \
      uint3 thread_position_in_threadgroup                                \
          [[thread_position_in_threadgroup]],                             \
      uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]])

// Verbatim prologue of laguna_prefill_router_tournament_ordinal_active64_v2.
#define RPROLOGUE                                                    \
  uint lane = thread_position_in_threadgroup.x;                      \
  uint row = threadgroup_position_in_grid.y;                         \
  threadgroup float original_scores[256];                            \
  float x = float(logits[row * 256 + lane]);                         \
  float y = 1.0f / (1.0f + metal::exp(metal::abs(x)));               \
  float score = x < 0.0f ? y : 1.0f - y;                             \
  original_scores[lane] = score;                                     \
  float key = -(score + float(correction_bias[lane]));               \
  uint my_ordinal = laguna_router_key_ordinal(key);                  \
  uint my_index = lane;

#define REPILOGUE                                                    \
  threadgroup_barrier(mem_flags::mem_threadgroup);                   \
  if (lane < 8) {                                                    \
    router_indices[row * 8 + lane] = my_index;                       \
    router_scores[row * 8 + lane] = original_scores[my_index];       \
  }

// Bitonic comparator, verbatim semantics from the scored kernel.
#define XCMP(stride_e, seq_e)                                        \
  {                                                                  \
    uint other_ordinal = simd_shuffle_xor(my_ordinal, ushort(stride_e)); \
    uint other_index = simd_shuffle_xor(my_index, ushort(stride_e)); \
    bool is_lower = (lane & (stride_e)) == 0;                        \
    bool lower_wants_better = (lane & (seq_e)) == 0;                 \
    bool want_better = lower_wants_better == is_lower;               \
    bool other_before_my = laguna_router_ordinal_before(             \
        other_ordinal, other_index, my_ordinal, my_index);           \
    bool take_other = want_better ? other_before_my : !other_before_my; \
    if (take_other) {                                                \
      my_ordinal = other_ordinal;                                    \
      my_index = other_index;                                        \
    }                                                                \
  }

// Monotone butterfly comparator, verbatim semantics from the scored kernel's
// final descending merge.
#define XCMP1(stride_e)                                              \
  {                                                                  \
    uint other_ordinal = simd_shuffle_xor(my_ordinal, ushort(stride_e)); \
    uint other_index = simd_shuffle_xor(my_index, ushort(stride_e)); \
    bool is_lower = (lane & (stride_e)) == 0;                        \
    bool other_before_my = laguna_router_ordinal_before(             \
        other_ordinal, other_index, my_ordinal, my_index);           \
    bool take_other = is_lower ? other_before_my : !other_before_my; \
    if (take_other) {                                                \
      my_ordinal = other_ordinal;                                    \
      my_index = other_index;                                        \
    }                                                                \
  }

#define BITONIC_UPTO(MAXSEQ)                                         \
  for (uint sequence = 2; sequence <= MAXSEQ; sequence <<= 1) {      \
    for (uint stride = sequence >> 1; stride > 0; stride >>= 1) {    \
      XCMP(stride, sequence)                                         \
    }                                                                \
  }

// Matched null: signature, prologue, barrier and epilogue only, zero comparator
// stages. One extra mask keeps my_ordinal live so the prologue is not
// dead-stripped -- without it the sigmoid and both loads disappear and the arm
// stops being a valid floor for the other arms.
RSIG(r_cmp00) {
  RPROLOGUE
  my_index = my_ordinal & 255u;
  REPILOGUE
}

// Comparator-stage ladder. 1 + 2 + 3 (+4) (+5) stages. Linear growth here is
// the folding detector: a collapsed chain would show a flat byte count.
RSIG(r_cmp06) {
  RPROLOGUE
  BITONIC_UPTO(8u)
  REPILOGUE
}

RSIG(r_cmp10) {
  RPROLOGUE
  BITONIC_UPTO(16u)
  REPILOGUE
}

// Identical to phase 1 of the scored kernel.
RSIG(r_cmp15) {
  RPROLOGUE
  BITONIC_UPTO(32u)
  REPILOGUE
}

// Explicitly unrolled comparator chains, same comparator bodies, same stage
// counts as the r_cmp* ladder. The r_cmp* ladder grows by a constant 144 B per
// extra `sequence` value rather than per comparator, which is the signature of
// a rolled inner stride loop. These arms separate "rolled" from "CSE": if the
// loop form is rolled, the unrolled form must be markedly larger and must grow
// linearly per comparator.
#define U_SEQ2 XCMP(1u, 2u)
#define U_SEQ4 XCMP(2u, 4u) XCMP(1u, 4u)
#define U_SEQ8 XCMP(4u, 8u) XCMP(2u, 8u) XCMP(1u, 8u)
#define U_SEQ16 XCMP(8u, 16u) XCMP(4u, 16u) XCMP(2u, 16u) XCMP(1u, 16u)
#define U_SEQ32                                                      \
  XCMP(16u, 32u) XCMP(8u, 32u) XCMP(4u, 32u) XCMP(2u, 32u) XCMP(1u, 32u)

RSIG(r_u01) { RPROLOGUE U_SEQ2 REPILOGUE }
RSIG(r_u03) { RPROLOGUE U_SEQ2 U_SEQ4 REPILOGUE }
RSIG(r_u06) { RPROLOGUE U_SEQ2 U_SEQ4 U_SEQ8 REPILOGUE }
RSIG(r_u10) { RPROLOGUE U_SEQ2 U_SEQ4 U_SEQ8 U_SEQ16 REPILOGUE }
RSIG(r_u15) { RPROLOGUE U_SEQ2 U_SEQ4 U_SEQ8 U_SEQ16 U_SEQ32 REPILOGUE }

// Monotone-comparator ladder. XCMP1 is the primitive the proposed Lever 2
// butterfly is built from, and it drops the two sequence-mask operands, so it
// must be priced separately from XCMP.
RSIG(r_m01) { RPROLOGUE XCMP1(1u) REPILOGUE }
RSIG(r_m03) { RPROLOGUE XCMP1(4u) XCMP1(2u) XCMP1(1u) REPILOGUE }
RSIG(r_m05) {
  RPROLOGUE XCMP1(16u) XCMP1(8u) XCMP1(4u) XCMP1(2u) XCMP1(1u) REPILOGUE
}

// Same nested loop as r_cmp15 but with full unrolling requested. If this lands
// on r_u15 rather than r_cmp15, the loop form really was rolled and static
// __compute bytes cannot see the dynamic comparator count.
RSIG(r_p15) {
  RPROLOGUE
#pragma clang loop unroll(full)
  for (uint sequence = 2; sequence <= 32u; sequence <<= 1) {
#pragma clang loop unroll(full)
    for (uint stride = sequence >> 1; stride > 0; stride >>= 1) {
      XCMP(stride, sequence)
    }
  }
  REPILOGUE
}

// C+D mock. C (simdgroup-0 extracts and broadcasts) is already banked in the
// scored kernel -- see the `active64` guards -- so what this arm mocks is D:
// stop the wide bitonic at sequence 8 (6 stages), publish one winner per
// aligned group of 8 lanes, then finish with a single 5-stage butterfly inside
// one simdgroup instead of the scored kernel's 15-stage 64-candidate sort plus
// 6-stage cross-simdgroup merge. 11 comparator stages against 36.
RSIG(r_cd_mock) {
  RPROLOGUE
  threadgroup uint xchg_ordinals[32];
  threadgroup uint xchg_indices[32];
  BITONIC_UPTO(8u)
  if ((lane & 7u) == 0u) {
    xchg_ordinals[lane >> 3] = my_ordinal;
    xchg_indices[lane >> 3] = my_index;
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (lane < 32) {
    my_ordinal = xchg_ordinals[lane];
    my_index = xchg_indices[lane];
    XCMP1(16u)
    XCMP1(8u)
    XCMP1(4u)
    XCMP1(2u)
    XCMP1(1u)
  }
  REPILOGUE
}
