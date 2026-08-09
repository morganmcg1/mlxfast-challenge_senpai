"""Characterise the M5 receipt channel from the public corpus.

The same-session baseline is identical code on every receipt, so bl_dec/bl_pre
form an n>1000 null sample of the measurement channel itself.
"""
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime

PATH = sys.argv[1] if len(sys.argv) > 1 else "research/r93-runs/receipts-latest.json"
r = json.load(open(PATH))
for x in r:
    x["t"] = datetime.strptime(x["ts"], "%Y-%m-%dT%H:%M:%SZ")
r.sort(key=lambda x: x["t"])


def cv(v):
    return 100 * st.stdev(v) / st.mean(v)


def chi2_ci(s, n, lo=0.025, hi=0.975):
    """Two-sided 95% CI for a standard deviation, n-1 dof, via Wilson-Hilferty."""
    df = n - 1

    def q(p):
        # Wilson-Hilferty inverse chi-square approximation
        z = _norm_ppf(p)
        return df * (1 - 2 / (9 * df) + z * math.sqrt(2 / (9 * df))) ** 3

    return s * math.sqrt(df / q(1 - lo)), s * math.sqrt(df / q(1 - hi))


def _norm_ppf(p):
    # Acklam's inverse normal CDF approximation
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    rr = q * q
    return (((((a[0] * rr + a[1]) * rr + a[2]) * rr + a[3]) * rr + a[4]) * rr + a[5]) * q / \
           (((((b[0] * rr + b[1]) * rr + b[2]) * rr + b[3]) * rr + b[4]) * rr + 1)


print("=" * 78)
print("1. BASELINE CHANNEL (identical code on every receipt)")
print("=" * 78)
print("span %s -> %s   n=%d" % (r[0]["ts"], r[-1]["ts"], len(r)))
for lab, key in [("bl_dec", "bl_dec"), ("bl_pre", "bl_pre")]:
    v = [x[key] * 1e6 for x in r]
    c = cv(v)
    lo, hi = chi2_ci(c, len(v))
    print("  %-7s mean %10.3f us  sd %8.3f  CV %.4f%%  95%% CI [%.4f%%, %.4f%%]"
          % (lab, st.mean(v), st.stdev(v), c, lo, hi))

print()
print("=" * 78)
print("2. TEMPORAL STRUCTURE: adjacent vs random pairs")
print("=" * 78)
random.seed(0)
for lab in ("bl_dec", "bl_pre"):
    v = [x[lab] * 1e6 for x in r]
    adj = [abs(v[i + 1] - v[i]) for i in range(len(v) - 1)]
    rnd = []
    for _ in range(50000):
        i, j = random.randrange(len(v)), random.randrange(len(v))
        if i != j:
            rnd.append(abs(v[i] - v[j]))
    print("  %-7s mean|adjacent diff| %8.3f   mean|random diff| %8.3f   ratio %.4f"
          % (lab, st.mean(adj), st.mean(rnd), st.mean(adj) / st.mean(rnd)))

print()
print("=" * 78)
print("3. WITHIN-SESSION cand/baseline correlation (solver-day de-meaned)")
print("=" * 78)
g = defaultdict(list)
for x in r:
    g[(x["solver"], x["ts"][:10])].append(x)
grp = [v for v in g.values() if len(v) >= 5]
print("  solver-day groups with n>=5: %d   receipts %d"
      % (len(grp), sum(len(v) for v in grp)))
for lab, ka, kb in [("decode", "cand_dec", "bl_dec"), ("prefill", "cand_pre", "bl_pre")]:
    A, B = [], []
    for v in grp:
        a = [x[ka] * 1e6 for x in v]
        b = [x[kb] * 1e6 for x in v]
        ma, mb = st.mean(a), st.mean(b)
        A += [z - ma for z in a]
        B += [z - mb for z in b]
    n = len(A)
    sa = (sum(z * z for z in A) / (n - 1)) ** 0.5
    sb = (sum(z * z for z in B) / (n - 1)) ** 0.5
    rho = (sum(x * y for x, y in zip(A, B)) / (n - 1)) / (sa * sb)
    se = 1 / math.sqrt(n - 3)
    lo = math.tanh(math.atanh(rho) - 1.96 * se)
    hi = math.tanh(math.atanh(rho) + 1.96 * se)
    print("  %-7s n=%d  sd(cand resid)=%8.3f  sd(bl resid)=%8.3f  corr=%+.4f  95%% CI [%+.4f,%+.4f]"
          % (lab, n, sa, sb, rho, lo, hi))

print()
print("=" * 78)
print("4. DISTRIBUTIONAL SHAPE OF THE BASELINE CHANNEL")
print("=" * 78)
for lab in ("bl_dec", "bl_pre"):
    v = sorted(x[lab] * 1e6 for x in r)
    n = len(v)
    m, s = st.mean(v), st.stdev(v)
    z = [(x - m) / s for x in v]
    kurt = sum(t ** 4 for t in z) / n - 3
    skew = sum(t ** 3 for t in z) / n
    k = int(0.05 * n)
    trimmed = v[k:n - k]
    print("  %-7s skew %+.3f  excess kurtosis %+.3f" % (lab, skew, kurt))
    print("          quantiles p1 %.2f p25 %.2f p50 %.2f p75 %.2f p99 %.2f"
          % (v[int(.01 * n)], v[int(.25 * n)], v[int(.5 * n)], v[int(.75 * n)], v[int(.99 * n)]))
    print("          full CV %.4f%%   5%%-trimmed CV %.4f%%   (robust sd/IQR) %.4f%%"
          % (cv(v), cv(trimmed),
             100 * (v[int(.75 * n)] - v[int(.25 * n)]) / 1.349 / m))

print()
print("=" * 78)
print("5. NOISE BUDGET AND MIN-RESOLVABLE DIFFERENCE")
print("=" * 78)
print("  corr(cand,bl)~0  =>  CV(published speedup)^2 = CV(cand)^2 + CV(bl)^2.")
print("  So comparing RAW candidate us is sqrt(2)x sharper than comparing")
print("  published speedups, for the same number of receipts.")
print()
# t critical values, two-sided 95%, df = 2(n-1) for a two-sample comparison
TCRIT = {2: 4.303, 3: 2.776, 4: 2.447, 5: 2.228, 6: 2.086, 7: 2.042, 8: 2.015,
         10: 1.972, 12: 1.960}


def tcrit(df):
    ks = sorted(TCRIT)
    for k in ks:
        if df <= k:
            return TCRIT[k]
    return 1.96


# Candidate-side CVs measured on THIS branch's machine-code-identical nulls
# (research/r93-runs/receipts/null-*.json). Overridden by measure_nulls() below
# when enough replicates have landed.
CAND_CV = {"decode": 0.4041, "prefill": 0.0643}
try:
    import glob
    nd, npre = [], []
    for f in sorted(glob.glob("research/r93-runs/receipts/null-*.json")):
        m = json.load(open(f))["submission"]["officialMetrics"]
        nd.append(m["decode_seconds_per_token"] * 1e6)
        npre.append(m["prefill_seconds_per_token"] * 1e6)
    if len(nd) >= 3:
        CAND_CV = {"decode": cv(nd), "prefill": cv(npre)}
        print("  candidate-side CV from %d machine-code-identical nulls:"
              " decode %.4f%%  prefill %.4f%%" % (len(nd), CAND_CV["decode"], CAND_CV["prefill"]))
except Exception as e:  # receipts not yet fetched
    print("  (using recorded candidate CVs; %s)" % e)
print()

for lab, kb in [("decode", "bl_dec"), ("prefill", "bl_pre")]:
    b = cv([x[kb] * 1e6 for x in r])
    c = CAND_CV[lab]
    pub_cv = math.sqrt(c * c + b * b)
    print("  --- %s: candidate-side CV %.4f%%   baseline-side CV %.4f%%"
          "   published-speedup CV %.4f%% ---" % (lab, c, b, pub_cv))
    print("      %-4s %-18s %-18s %s" % ("n", "raw cand us", "published su", "sharpening"))
    for n in (2, 3, 4, 6, 8):
        t = tcrit(2 * (n - 1))
        raw = t * c * math.sqrt(2.0 / n)
        pub = t * pub_cv * math.sqrt(2.0 / n)
        print("      %-4d %8.4f%%          %8.4f%%          %5.1fx" % (n, raw, pub, pub / raw))
    print()

print("=" * 78)
print("6. SUBMISSION CADENCE: receipts needed to confirm a true decode win")
print("=" * 78)
Z_A, Z_B = 1.959964, 0.8416212  # 95% two-sided, 80% power
c = CAND_CV["decode"]
b = cv([x["bl_dec"] * 1e6 for x in r])
pub_cv = math.sqrt(c * c + b * b)
print("  sigma(raw candidate decode)   = %.4f%%" % c)
print("  sigma(published decode su)    = %.4f%%" % pub_cv)
print()
print("  %-10s %-28s %-28s" % ("true delta", "vs an ESTABLISHED reference",
                               "vs a FRESH 1-receipt reference"))
print("  %-10s %-13s %-14s %-13s %-14s" % ("", "raw us", "published su", "raw us", "published su"))
for d in (0.5, 1.0, 2.0, 4.0):
    def need(sig, k):
        return max(1, math.ceil(k * (Z_A + Z_B) ** 2 * sig * sig / (d * d)))
    print("  %-10s %-13d %-14d %-13d %-14d"
          % ("%.1f %%" % d, need(c, 1), need(pub_cv, 1), need(c, 2), need(pub_cv, 2)))
print()
print("  'established reference' = the frontier already has many receipts, so only")
print("  the new candidate must be replicated. 'fresh' = both arms bought new.")
print("  At ~21 min turnaround on a strictly serial channel, the right-hand")
print("  columns are the real cost of a claim.")
