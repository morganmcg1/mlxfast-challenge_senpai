"""Fit the M5 Max constants from the config A / config B official receipts.

Usage: python3 research/tanjiro-b-fit.py <prefill_spt_B> <decode_spt_B>
"""
import sys

S = lambda p: 512000 * p
T = lambda d, s: 1000 * d - s / 128

SA, TA = 103.5678, 4.83241          # receipt ff29f5c2
BASE_S, BASE_T = 189.0284, 12.40369  # same-session pinned baseline
SWEEP_MB = 268.435456                # bytes per pass, MB
GEMM_GFLOP = 17.179869184            # per injected GEMM
EXTRA_PASSES, EXTRA_GEMMS = 6, 100

# advisor roofline inputs (PR #27 body): prefill compute 47.16 ms at 60 TFLOP/s,
# prefill DRAM 34.32 ms at 500 GB/s, uninjected prefill 98.153 ms
ADV_FLOP_GFLOP = 60e3 * 47.16e-3
ADV_BYTES_GB = 500 * 34.32e-3
S0 = 96.8  # our base's ranked prefill, from the five best published receipts

sb = S(float(sys.argv[1]))
tb = T(float(sys.argv[2]), sb)
dt, ds = tb - TA, sb - SA
bw = EXTRA_PASSES * SWEEP_MB / 1e3 / (dt / 1e3)
tf = EXTRA_GEMMS * GEMM_GFLOP / 1e3 / (ds / 1e3)

print("config B receipt: S_B=%.4f ms  T_B=%.5f ms" % (sb, tb))
print("  dT = %+.5f ms  ->  DRAM  = %.1f GB/s" % (dt, bw))
print("  dS = %+.4f ms  ->  GEMM  = %.3f TFLOP/s at 512x8192x2048" % (ds, tf))
print("  speedups: prefill %.4f  decode %.4f  (floors need >= 0.95)"
      % (BASE_S / sb, BASE_T / tb))
print()
compute_ms = ADV_FLOP_GFLOP / tf
dram_ms = ADV_BYTES_GB / bw * 1e3
print("prefill overlap+glue, advisor's fourth constant:")
print("  compute %.2f ms (%.0f GFLOP at %.3f TFLOP/s)" % (compute_ms, ADV_FLOP_GFLOP, tf))
print("  dram    %.2f ms (%.2f GB at %.1f GB/s)" % (dram_ms, ADV_BYTES_GB, bw))
print("  S_0 - max(compute, dram) = %.2f - %.2f = %+.2f ms  (assumed 9-12 ms)"
      % (S0, max(compute_ms, dram_ms), S0 - max(compute_ms, dram_ms)))
