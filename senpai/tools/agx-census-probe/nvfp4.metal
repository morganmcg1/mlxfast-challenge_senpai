// S4-b: NVFP4 code->float reconstruction at real kernel scale, on both targets.
// Research only. Self-contained: compile directly with census.sh.
//
// The advisor's R89 §5b table compared "ALU reconstruct", "constant float* LUT"
// and "NVFP4 sign/magnitude" over a toy 8-code loop. None of those three is the
// variant the runtime actually ships. The shipping path builds `half2` bit
// patterns straight out of the nibbles and reinterprets them
// (LagunaRuntimeModel.swift:6596-6692, `packedWordBody`), and it has three live
// arms selected by `lagunaNvfp4NibbleSplit` (0 = default, 1, 2). Those three are
// censused here as BP0/BP1/BP2, verbatim, against LUT and sign/magnitude.
//
// Scale: one arm iteration is a full `laguna_nvfp4_qdot_codes_16` equivalent
// (16 codes, two packed words). Arms come in 4-group (64-code) and 8-group
// (128-code) sizes so the marginal cost per 64 codes is folding-immune: a
// collapsed or rolled arm shows a flat or sublinear step instead.

#include <metal_stdlib>
using namespace metal;

// Verbatim from the `default` case of the runtime's `extract` switch.
#define BP0(c)                                                       \
  const uint p0 = ((c & 0x00070007u) << 9) | ((c & 0x00080008u) << 12); \
  const uint p1 = ((c & 0x00700070u) << 5) | ((c & 0x00800080u) << 8);   \
  const uint p2 = ((c & 0x07000700u) << 1) | ((c & 0x08000800u) << 4);   \
  const uint p3 = ((c & 0x70007000u) >> 3) | (c & 0x80008000u);

// Verbatim from `case 1` (nibble-split form).
#define BP1(c)                                                       \
  const uint xe = c & 0x0F0F0F0Fu;                                   \
  const uint ge = xe | (xe << 3);                                    \
  const uint yo = c & 0xF0F0F0F0u;                                   \
  const uint go = yo | (yo >> 3);                                    \
  const uint p0 = (ge << 9) & 0x8E008E00u;                           \
  const uint p1 = (go << 8) & 0x8E008E00u;                           \
  const uint p2 = (ge << 1) & 0x8E008E00u;                           \
  const uint p3 = go & 0x8E008E00u;

// Verbatim from `case 2` (shift-first form).
#define BP2(c)                                                       \
  const uint p0 = ((c << 9) & 0x0E000E00u) | ((c << 12) & 0x80008000u); \
  const uint p1 = ((c << 5) & 0x0E000E00u) | ((c << 8) & 0x80008000u);  \
  const uint p2 = ((c << 1) & 0x0E000E00u) | ((c << 4) & 0x80008000u);  \
  const uint p3 = ((c >> 3) & 0x0E000E00u) | (c & 0x80008000u);

// Shared tail of the shipping path: four half2 reinterprets, eight converts,
// eight multiply-adds, in the runtime's exact association.
#define BP_TAIL(base)                                                \
  const float2 v04 = float2(as_type<half2>(p0));                     \
  const float2 v15 = float2(as_type<half2>(p1));                     \
  const float2 v26 = float2(as_type<half2>(p2));                     \
  const float2 v37 = float2(as_type<half2>(p3));                     \
  accum += (input[(base) + 0] * v04.x + input[(base) + 1] * v15.x +   \
            input[(base) + 2] * v26.x + input[(base) + 3] * v37.x);   \
  accum += (input[(base) + 4] * v04.y + input[(base) + 5] * v15.y +   \
            input[(base) + 6] * v26.y + input[(base) + 7] * v37.y);

#define BP_WORD(VARIANT, c, base) { VARIANT(c) BP_TAIL(base) }

// E2M1 magnitudes with sign folded in, indexed by the raw 4-bit code.
constant float nvfp4_lut[16] = {0.0f,  0.5f,  1.0f,  1.5f,  2.0f,  3.0f,
                                4.0f,  6.0f,  -0.0f, -0.5f, -1.0f, -1.5f,
                                -2.0f, -3.0f, -4.0f, -6.0f};
constant float nvfp4_mag[8] = {0.0f, 0.5f, 1.0f, 1.5f, 2.0f, 3.0f, 4.0f, 6.0f};

#define LUT_WORD(c, base)                                            \
  {                                                                  \
    accum += input[(base) + 0] * nvfp4_lut[((c) >> 0) & 15u];        \
    accum += input[(base) + 1] * nvfp4_lut[((c) >> 4) & 15u];        \
    accum += input[(base) + 2] * nvfp4_lut[((c) >> 8) & 15u];        \
    accum += input[(base) + 3] * nvfp4_lut[((c) >> 12) & 15u];       \
    accum += input[(base) + 4] * nvfp4_lut[((c) >> 16) & 15u];       \
    accum += input[(base) + 5] * nvfp4_lut[((c) >> 20) & 15u];       \
    accum += input[(base) + 6] * nvfp4_lut[((c) >> 24) & 15u];       \
    accum += input[(base) + 7] * nvfp4_lut[((c) >> 28) & 15u];       \
  }

// Sign/magnitude: 8-entry magnitude table plus a sign applied by xor on the
// float bit pattern, which is what makes it a different instruction mix from a
// single signed 16-entry table.
#define SM_ONE(c, sh, base, off)                                     \
  {                                                                  \
    const uint n = ((c) >> (sh)) & 15u;                              \
    const float m = nvfp4_mag[n & 7u];                               \
    const float v = as_type<float>(as_type<uint>(m) | ((n & 8u) << 28)); \
    accum += input[(base) + (off)] * v;                              \
  }

#define SM_WORD(c, base)                                             \
  {                                                                  \
    SM_ONE(c, 0, base, 0) SM_ONE(c, 4, base, 1)                      \
    SM_ONE(c, 8, base, 2) SM_ONE(c, 12, base, 3)                     \
    SM_ONE(c, 16, base, 4) SM_ONE(c, 20, base, 5)                    \
    SM_ONE(c, 24, base, 6) SM_ONE(c, 28, base, 7)                    \
  }

#define NSIG(name)                                                   \
  [[kernel]] void name(                                              \
      const device uint* codes [[buffer(0)]],                        \
      const device float* input [[buffer(1)]],                       \
      device float* out [[buffer(2)]],                               \
      uint tid [[thread_position_in_grid]])

// Loads and accumulator live across the whole body, so register pressure tracks
// the real QMV inner loop rather than a toy loop over one word.
#define NPRO                                                         \
  float accum = 0.0f;                                                \
  const uint b = tid * 16u;                                          \
  uint c00 = codes[b + 0], c01 = codes[b + 1];                       \
  uint c02 = codes[b + 2], c03 = codes[b + 3];                       \
  uint c04 = codes[b + 4], c05 = codes[b + 5];                       \
  uint c06 = codes[b + 6], c07 = codes[b + 7];                       \
  uint c08 = codes[b + 8], c09 = codes[b + 9];                       \
  uint c10 = codes[b + 10], c11 = codes[b + 11];                     \
  uint c12 = codes[b + 12], c13 = codes[b + 13];                     \
  uint c14 = codes[b + 14], c15 = codes[b + 15];

#define NEPI out[tid] = accum;

// Matched null: identical signature, identical loads, identical store. Keeps
// every code word live with a cheap integer fold so the reconstruct arms are
// measured against a floor that really paid for the loads.
NSIG(n_null) {
  NPRO
  uint f = c00 ^ c01 ^ c02 ^ c03 ^ c04 ^ c05 ^ c06 ^ c07;
  f ^= c08 ^ c09 ^ c10 ^ c11 ^ c12 ^ c13 ^ c14 ^ c15;
  accum += float(f & 1u) * input[0];
  NEPI
}

#define ARM4(VARIANT)                                                \
  VARIANT(c00, 0) VARIANT(c01, 8) VARIANT(c02, 16) VARIANT(c03, 24)   \
  VARIANT(c04, 32) VARIANT(c05, 40) VARIANT(c06, 48) VARIANT(c07, 56)

#define ARM8(VARIANT)                                                \
  ARM4(VARIANT)                                                      \
  VARIANT(c08, 64) VARIANT(c09, 72) VARIANT(c10, 80) VARIANT(c11, 88) \
  VARIANT(c12, 96) VARIANT(c13, 104) VARIANT(c14, 112)                \
  VARIANT(c15, 120)

#define BP0_WORD(c, base) BP_WORD(BP0, c, base)
#define BP1_WORD(c, base) BP_WORD(BP1, c, base)
#define BP2_WORD(c, base) BP_WORD(BP2, c, base)

NSIG(n_bp0_4) { NPRO ARM4(BP0_WORD) NEPI }
NSIG(n_bp0_8) { NPRO ARM8(BP0_WORD) NEPI }
NSIG(n_bp1_4) { NPRO ARM4(BP1_WORD) NEPI }
NSIG(n_bp1_8) { NPRO ARM8(BP1_WORD) NEPI }
NSIG(n_bp2_4) { NPRO ARM4(BP2_WORD) NEPI }
NSIG(n_bp2_8) { NPRO ARM8(BP2_WORD) NEPI }
NSIG(n_lut_4) { NPRO ARM4(LUT_WORD) NEPI }
NSIG(n_lut_8) { NPRO ARM8(LUT_WORD) NEPI }
NSIG(n_sm_4) { NPRO ARM4(SM_WORD) NEPI }
NSIG(n_sm_8) { NPRO ARM8(SM_WORD) NEPI }
