import csv, collections
import sys
rows = list(csv.reader(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pr35_lm_census.csv")))
quad = [r for r in rows if r[0] == 'quad']
disp = [r for r in rows if r[0] == 'disp']
qa = sum(int(r[6]) for r in quad)
qb = sum(int(r[7]) for r in quad)
print("layers=%d lane_words=%d const_quad=%d frac=%.6f" % (len(quad), qa, qb, qb / qa))
tot_rows = sum(int(r[3]) for r in quad)
tot_fit = sum(int(r[4]) for r in quad)
print("rows=%d fittingRows=%d escaped=%d escaped_frac=%.6f"
      % (tot_rows, tot_fit, tot_rows - tot_fit, (tot_rows - tot_fit) / tot_rows))
g_fit = collections.Counter()
g_all = collections.Counter()
for r in disp:
    g_fit[int(r[5])] += int(r[6])
    g_all[int(r[5])] += int(r[7])
zero_all = [g for g in range(128) if g_all[g] == 0]
zero_fit = [g for g in range(128) if g_fit[g] == 0]
print("zero_all=%d zero_fit=%d identical=%s all_even_ge2=%s"
      % (len(zero_all), len(zero_fit), zero_all == zero_fit,
         zero_all == list(range(2, 128, 2))))
odd = list(range(1, 128, 2))
ov = [g_all[g] for g in odd]
print("odd min=%d (g=%d) max=%d (g=%d) frac %.4f..%.4f"
      % (min(ov), odd[ov.index(min(ov))], max(ov), odd[ov.index(max(ov))],
         min(ov) / tot_rows, max(ov) / tot_rows))
print("g0 all=%d fit=%d frac=%.6f" % (g_all[0], g_fit[0], g_all[0] / tot_rows))
print("sum_all=%d sum_fit=%d" % (sum(g_all.values()), sum(g_fit.values())))
pe = tot_rows * 128
print("plane_entries=%d mean_frac_all=%.6f mean_frac_fit=%.6f"
      % (pe, sum(g_all.values()) / pe, sum(g_fit.values()) / (tot_fit * 128)))
pl = [int(r[7]) / int(r[6]) for r in quad]
print("const_quad per-layer first8: " + " ".join("%.4f" % v for v in pl[:8]))
print("const_quad per-layer min=%.4f max=%.4f" % (min(pl), max(pl)))
print("row-shape histogram: %s" % dict(collections.Counter(int(r[3]) for r in quad)))

# `dhist` records the signed code delta s[(g+1)&127] - s[g], clamped to +-16,
# split by the parity of g. Scale codes are uint8 E4M3, so one code step is a
# mantissa step: eight byte patterns per octave, i.e. a magnitude ratio of
# 2**(delta/8) to within the 1.0667..1.125 per-step spread. That converts the
# addressing displacement of probe 128 into a relative weight error.
dh = [r for r in rows if r[0] == 'dhist']
if dh:
    even = collections.Counter()
    odd = collections.Counter()
    for r in dh:
        even[int(r[5])] += int(r[6])
        odd[int(r[5])] += int(r[7])

    def summarize(name, h):
        n = sum(h.values())
        if n == 0:
            return
        zero = h[0] / n
        sat = (h[-16] + h[16]) / n
        mad = sum(abs(d) * c for d, c in h.items()) / n
        rms = (sum(d * d * c for d, c in h.items()) / n) ** 0.5
        err = {d: 2.0 ** (d / 8.0) - 1.0 for d in h}
        mae = sum(abs(err[d]) * c for d, c in h.items()) / n
        rmse = (sum(err[d] * err[d] * c for d, c in h.items()) / n) ** 0.5
        print("%s n=%d zero=%.6f sat16=%.6f mean|d|=%.4f rms_d=%.4f "
              "mean|rel|=%.4f rms_rel=%.4f" % (name, n, zero, sat, mad, rms, mae, rmse))

    summarize("dhist even_g", even)
    summarize("dhist  odd_g", odd)
    both = collections.Counter(even)
    both.update(odd)
    summarize("dhist  all_g", both)
    top = sorted(odd.items(), key=lambda kv: -kv[1])[:9]
    print("odd_g top deltas: " + " ".join("%+d:%.4f" % (d, c / sum(odd.values()))
                                          for d, c in top))

# `derr` carries the exact per-entry relative error |s[(g+1)&127]/s[g] - 1|
# accumulated in the runtime with a bias-7 E4M3 decode, so it needs no
# approximation: fields are parity, n, sum|rel|, sum rel^2, max|rel|, zero-denom.
de = [r for r in rows if r[0] == 'derr']
if de:
    for p, name in ((0, "even_g"), (1, " odd_g")):
        sel = [r for r in de if int(r[5]) == p]
        n = sum(int(r[6]) for r in sel)
        sa = sum(float(r[7]) for r in sel)
        sq = sum(float(r[8]) for r in sel)
        mx = max(float(r[9]) for r in sel)
        z = sum(int(r[10]) for r in sel)
        print("derr %s n=%d zero_denom=%d mean|rel|=%.6f rms_rel=%.6f max|rel|=%.4f"
              % (name, n, z, sa / n, (sq / n) ** 0.5, mx))
    n = sum(int(r[6]) for r in de)
    sa = sum(float(r[7]) for r in de)
    sq = sum(float(r[8]) for r in de)
    print("derr  all_g n=%d mean|rel|=%.6f rms_rel=%.6f" % (n, sa / n, (sq / n) ** 0.5))

ch = [r for r in rows if r[0] == 'chist']
if ch:
    codes = collections.Counter()
    for r in ch:
        codes[int(r[5])] += int(r[6]) + int(r[7])
    n = sum(codes.values())
    sub = sum(c for k, c in codes.items() if 1 <= k <= 7)
    print("chist n=%d distinct=%d min=%d max=%d zero=%.6f subnormal(1..7)=%.6f "
          "signbit=%.6f" % (n, len(codes), min(codes), max(codes),
                            codes[0] / n, sub / n,
                            sum(c for k, c in codes.items() if k >= 128) / n))
    print("chist top codes: " + " ".join("%d:%.4f" % (k, c / n) for k, c in
                                        sorted(codes.items(), key=lambda kv: -kv[1])[:10]))
