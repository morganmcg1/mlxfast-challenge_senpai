"""Fit the M5 Max constants from the config A / config B official receipts.

Both receipts are in, so the inputs are hardcoded and this is a derivation of
record rather than a calculator. Each constant is reported twice: raw, and
normalised by the ratio of the two sessions' own pinned baselines. The pinned
baseline is byte-identical code in both sessions, so its drift measures the
session clock, and normalising removes it under a pure-scale-factor model.
"""

S = lambda p: 512000 * p
T = lambda d, s: 1000 * d - s / 128

# receipt ff29f5c2 -- config A: 1 sweep pass/step, 20 injected GEMMs/forward
PA, DA = 0.00020228084375, 0.005641537109375
BASE_PA, BASE_DA = 0.000369196126953125, 0.013880474609375
# receipt 553ef9f0 -- config B: 7 sweep passes/step, 120 injected GEMMs/forward
PB, DB = 0.000266209716796875, 0.00849359928125
BASE_PB, BASE_DB = 0.0003828357734375, 0.013828389328125

SWEEP_MB = 268.435456      # 1 << 24 uint4 = 256 MiB, one pass over the pool
GEMM_GFLOP = 17.179869184  # 2 * 512 * 8192 * 2048, one injected bf16 GEMM
EXTRA_PASSES, EXTRA_GEMMS = 6, 100

# observed sd of the pinned baseline across the public feed, per receipt
SD_T, SD_S = 0.0034, 0.0193

# prefill roofline for the uninjected forward (fern's totals via the #27 body)
ROOFLINE_GFLOP = 2829.5
ROOFLINE_GB = 17.16
S0 = 96.8            # our base's ranked prefill, five best published receipts
FRONTIER_T = 4.3224  # our frontier's decode step
FRONTIER_MB = 1794   # its byte budget per token

SA, TA = S(PA), T(DA, S(PA))
SB, TB = S(PB), T(DB, S(PB))
BSA, BTA = S(BASE_PA), T(BASE_DA, S(BASE_PA))
BSB, BTB = S(BASE_PB), T(BASE_DB, S(BASE_PB))


def constants(sa, ta, label):
    dt, ds = TB - ta, SB - sa
    bw = EXTRA_PASSES * SWEEP_MB / dt   # MB/ms == GB/s
    tf = EXTRA_GEMMS * GEMM_GFLOP / ds  # GFLOP/ms == TFLOP/s
    compute, dram = ROOFLINE_GFLOP / tf, ROOFLINE_GB * 1e3 / bw
    print(label)
    print("  A: S=%9.4f T=%8.5f      B: S=%9.4f T=%8.5f" % (sa, ta, SB, TB))
    print("  dT = %+.5f ms  ->  streaming DRAM read = %.1f GB/s" % (dt, bw))
    print("  dS = %+.4f ms  ->  dense bf16 GEMM     = %.2f TFLOP/s" % (ds, tf))
    print("  prefill roofline at those rates: compute %.2f ms, dram %.2f ms" % (compute, dram))
    print("    S_0 - max(compute, dram) = %.2f - %.2f = %+.2f ms  (%.0f%% of S_0)"
          % (S0, max(compute, dram), S0 - max(compute, dram),
             100 * (S0 - max(compute, dram)) / S0))
    return bw, tf


print("session baselines (byte-identical code, so this is session drift):")
print("  A: S=%9.4f T=%8.5f      B: S=%9.4f T=%8.5f" % (BSA, BTA, BSB, BTB))
print("  ratio B/A:  S %.6f   T %.6f" % (BSB / BSA, BTB / BTA))
print("gates: A prefill %.5f decode %.5f | B prefill %.5f decode %.5f (floor 0.95)"
      % (BSA / SA, BTA / TA, BSB / SB, BTB / TB))
print()
bw_raw, tf_raw = constants(SA, TA, "RAW (each receipt as published)")
print()
bw_n, tf_n = constants(SA * BSB / BSA, TA * BTB / BTA,
                       "SESSION-NORMALISED (A rescaled onto B's clock)")
print()
edt = ((SD_T * TA) ** 2 + (SD_T * TB) ** 2) ** 0.5
eds = ((SD_S * SA) ** 2 + (SD_S * SB) ** 2) ** 0.5
rbw, rtf = bw_raw * edt / (TB - TA), tf_raw * eds / (SB - SA)
print("statistical uncertainty propagated from the feed's own baseline sd:")
print("  dT %+.5f ms -> +-%.4f ms (%.2f%%)  =>  DRAM +-%.0f GB/s"
      % (TB - TA, edt, 100 * edt / (TB - TA), rbw))
print("  dS %+.4f ms -> +-%.4f ms (%.2f%%)  =>  GEMM +-%.1f TFLOP/s"
      % (SB - SA, eds, 100 * eds / (SB - SA), rtf))
print()
lo_bw, hi_bw = min(bw_raw, bw_n) - rbw, max(bw_raw, bw_n) + rbw
lo_tf, hi_tf = min(tf_raw, tf_n) - rtf, max(tf_raw, tf_n) + rtf
print("REPORTED BANDS (raw/normalised pair widened by the sd):")
print("  achievable streaming DRAM read      %.0f - %.0f GB/s" % (lo_bw, hi_bw))
print("  dense bf16 GEMM at 512x8192x2048    %.1f - %.1f TFLOP/s" % (lo_tf, hi_tf))
print()
print("decode: %d MB/token at frontier T=%.4f ms = %.0f GB/s = %.0f-%.0f%% of ceiling"
      % (FRONTIER_MB, FRONTIER_T, FRONTIER_MB / FRONTIER_T,
         100 * (FRONTIER_MB / FRONTIER_T) / hi_bw,
         100 * (FRONTIER_MB / FRONTIER_T) / lo_bw))
print("prefill: %.1f GFLOP / S_0 %.1f ms = %.2f TFLOP/s = %.0f-%.0f%% of the GEMM rate"
      % (ROOFLINE_GFLOP, S0, ROOFLINE_GFLOP / S0,
         100 * (ROOFLINE_GFLOP / S0) / hi_tf, 100 * (ROOFLINE_GFLOP / S0) / lo_tf))
