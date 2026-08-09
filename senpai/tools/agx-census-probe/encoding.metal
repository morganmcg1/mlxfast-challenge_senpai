// AGX encoding-length study (research only).
//
// Question: is "__compute bytes / 8" a valid instruction estimator?
//
// Every arm below has the identical signature and the identical live-argument
// set (both input buffers are read, both output buffers are written), so the
// prologue/epilogue floor is shared and `e_null` is an exact matched null.
// Each arm then adds exactly N operations of one opcode class.
//
// Only classes that cannot be algebraically collapsed under -fno-fast-math are
// included. The N = 32/64/128 ladder is itself the collapse detector: a
// collapsed chain shows a flat byte count across N.
#include <metal_stdlib>
using namespace metal;

#define SIG(name)                                          \
  kernel void name(const device float* fin [[buffer(0)]],   \
                   const device uint* uin [[buffer(1)]],    \
                   device float* fout [[buffer(2)]],        \
                   device uint* uout [[buffer(3)]],         \
                   uint tid [[thread_position_in_grid]])

#define PROLOGUE                 \
  float a = fin[tid + 0];        \
  float b = fin[tid + 1];        \
  float c = fin[tid + 2];        \
  uint x = uin[tid + 0];         \
  uint y = uin[tid + 1];         \
  uint z = uin[tid + 2];

#define EPILOGUE                 \
  fout[tid] = a;                 \
  uout[tid] = x;

// float FMA, all three operands in registers
#define ARM_FFMA(name, N)                    \
  SIG(name) {                                \
    PROLOGUE                                 \
    for (uint i = 0; i < N; ++i) {           \
      a = fma(a, b, c);                      \
    }                                        \
    EPILOGUE                                 \
  }

// float add, both operands in registers
#define ARM_FADD(name, N)                    \
  SIG(name) {                                \
    PROLOGUE                                 \
    for (uint i = 0; i < N; ++i) {           \
      a = a + b;                             \
    }                                        \
    EPILOGUE                                 \
  }

// float FMA with a loop-varying immediate addend (the shape used by the
// original calibration ladder, kept here under a matched signature)
#define ARM_FIMM(name, N)                    \
  SIG(name) {                                \
    PROLOGUE                                 \
    for (uint i = 0; i < N; ++i) {           \
      a = fma(a, b, float(i));               \
    }                                        \
    (void)c;                                 \
    EPILOGUE                                 \
  }

// integer multiply-add, all operands in registers
#define ARM_IMAD(name, N)                    \
  SIG(name) {                                \
    PROLOGUE                                 \
    for (uint i = 0; i < N; ++i) {           \
      x = x * y + z;                         \
    }                                        \
    EPILOGUE                                 \
  }

SIG(e_null) {
  PROLOGUE
  (void)b;
  (void)c;
  (void)y;
  (void)z;
  EPILOGUE
}

ARM_FFMA(e_ffma_032, 32)
ARM_FFMA(e_ffma_064, 64)
ARM_FFMA(e_ffma_128, 128)

ARM_FADD(e_fadd_032, 32)
ARM_FADD(e_fadd_064, 64)
ARM_FADD(e_fadd_128, 128)

ARM_FIMM(e_fimm_032, 32)
ARM_FIMM(e_fimm_064, 64)
ARM_FIMM(e_fimm_128, 128)

ARM_IMAD(e_imad_032, 32)
ARM_IMAD(e_imad_064, 64)
ARM_IMAD(e_imad_128, 128)
