"""Fit the saturation law ΔX(n) = max(0, n*c - slack) for decode and prefill axes."""
import statistics as st

S = lambda p: 512000 * p
T = lambda d, s: 1000 * d - s / 128

li_s = S(0.00180222371484375)
li_t = T(0.016330572921875, li_s)
print("LI  prefill=100000 tg160: S=%.3f  T=%.5f" % (li_s, li_t))

b2 = [575.182, 562.166, 576.764, 573.317]  # batch-2 runs with prefill empties = 0
m2 = st.mean(b2)
print("batch2 prefill0 S: mean=%.3f sd=%.3f (%.2f%%)" % (m2, st.stdev(b2), 100 * st.stdev(b2) / m2))

ld = 588.450  # prefill empties = 20000
c160 = 2.804e-3  # ms per dispatch, tg=160, from the decode axis
print("LD(20000) dS vs batch2 = %+.2f ms; serialized = %.1f ms; absorbed = %.1f ms"
      % (ld - m2, 20000 * c160, 20000 * c160 - (ld - m2)))

for ref, name in ((m2, "batch2"), (614.827, "LA3")):
    slack = 20000 * c160 - (ld - ref)
    c = (li_s - ref + slack) / 100000 * 1000
    print("  ref=%s(%.1f): prefill slack=%.1f ms (knee=%.0f disp); c_prefill(LI)=%.3f us"
          % (name, ref, slack, slack / c160, c))

la3 = 10.11366  # config-A reference: sweeps=1, matmuls=20, no empties
for tg, pts in ((8, [(2000, 11.22364), (8000, 27.05580)]),
                (160, [(2000, 10.93761), (4000, 16.54604)])):
    (n1, t1), (n2, t2) = pts
    c = (t2 - t1) / (n2 - n1) * 1000
    slack = n2 * c / 1000 - (t2 - la3)
    print("decode tg=%d: c=%.3f us  slack=%.3f ms  knee=%.0f disp" % (tg, c, slack, slack * 1000 / c))
