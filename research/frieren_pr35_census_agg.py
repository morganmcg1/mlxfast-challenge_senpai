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
