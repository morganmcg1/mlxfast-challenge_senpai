// AGX census calibration ladder (research only).
//
// k_empty  : signature floor with one live load and one live store.
// k_fma00/30/60/480 : linearity ladder for an immediate-operand FMA chain.
// k_fold   : folding hazard detector. The accumulator overflows to inf and the
//            compiler is free to drop the load entirely, so this arm must come
//            in at or below k_empty. If it does not, the compiler kept the work
//            and a "constant-folded away" reading of a small delta is wrong.
#include <metal_stdlib>
using namespace metal;

#define SIG(name)                                     \
  kernel void name(const device float* in [[buffer(0)]], \
                   device float* out [[buffer(1)]],      \
                   uint tid [[thread_position_in_grid]])

#define LADDER(N)               \
  for (uint i = 0; i < N; ++i) { \
    s = fma(s, w, float(i));     \
  }

SIG(k_empty) { out[tid] = in[tid]; }

SIG(k_fma00) {
  float s = in[tid];
  float w = 1.0000001f;
  LADDER(0)
  out[tid] = s;
}

SIG(k_fma30) {
  float s = in[tid];
  float w = 1.0000001f;
  LADDER(30)
  out[tid] = s;
}

SIG(k_fma60) {
  float s = in[tid];
  float w = 1.0000001f;
  LADDER(60)
  out[tid] = s;
}

SIG(k_fma480) {
  float s = in[tid];
  float w = 1.0000001f;
  LADDER(480)
  out[tid] = s;
}

SIG(k_fold) {
  float s = in[tid];
  for (uint i = 0; i < 480; ++i) {
    s = s * 1e30f + 1e30f;
  }
  out[tid] = s;
}
