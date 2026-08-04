"""M4 gate of the shipped config-B magnitudes (7 sweep passes, 120 prefill GEMMs)."""
S = lambda p: 512000 * p
T = lambda d, s: 1000 * d - s / 128

# config A on this host (sweeps 1 pass, 20 GEMMs), section 6
sa, ta = 614.827, 10.11366
sb = S(0.001667633951171875)
tb = T(0.023568192703125, sb)
print("M4 config B: S=%.3f ms  T=%.5f ms" % (sb, tb))
print("  dT = %+.5f ms over 6 extra passes -> BW = %.1f GB/s"
      % (tb - ta, 6 * 0.268435456 / ((tb - ta) / 1000)))
print("  dS = %+.3f ms over 100 extra GEMMs -> %.3f TFLOP/s"
      % (sb - sa, 100 * 17.179869184 / ((sb - sa) / 1000) / 1e3))
print("  (same-batch prefill-0 mean 571.857 ms reference: dS=%+.3f -> %.3f TFLOP/s)"
      % (sb - 571.857, 100 * 17.179869184 / ((sb - 571.857) / 1000) / 1e3))
print()
print("prior M4 small-lever values: BW 256.20 GB/s, FLOP 7.40-7.46 TFLOP/s")
