import math

# research/RESEARCH_STATE_ARCHIVE_through-round-21.md:5684-5695 at advisor head 6778867d
# columns: time, sha, T, S, ns(=candidate score cs), draw(=official/cs), score(=official)
rows = [
    ("07:53", "27b9c7c6", 2.51567, 0.992674, 2.497243),
    ("09:30", "f8502e12", 2.51417, 0.988626, 2.485577),
    ("10:02", "71586bcf", 2.51065, 1.002111, 2.515950),
    ("10:26", "f3cda678", 2.51374, 0.998094, 2.508953),
    ("10:49", "5d522d6a", 2.52060, 0.988443, 2.491470),
    ("11:15", "5e0e9cd1", 2.51302, 0.994854, 2.500092),
    ("11:38", "c210d200", 2.52110, 0.997477, 2.514743),
    ("14:16", "0c21dc18", 2.52973, 0.985211, 2.492321),
    ("14:48", "2dce5912", 2.52967, 0.985388, 2.492708),
    ("15:10", "7a5a1e08", 2.51083, 0.998492, 2.507043),
    ("15:34", "1feeabc8", 2.52274, 0.991135, 2.500378),
    ("16:06", "ff29f5c2", 2.30788, 0.989388, 2.283393),
]


def stats(xs):
    n = len(xs)
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return n, m, math.sqrt(v)


print("CHECK: printed draw vs official/cs, per row (ppm)")
worst = 0.0
for t, sha, cs, draw, off in rows:
    rec = off / cs
    ppm = (rec / draw - 1) * 1e6
    worst = max(worst, abs(ppm))
    print("  %s %s draw=%.6f recomputed=%.8f  %+9.2f ppm" % (t, sha, draw, rec, ppm))
print("  worst |ppm| = %.2f" % worst)

L = [r[3] for r in rows]
lnL = [math.log(x) for x in L]
n, m, sd = stats(lnL)
print("\nALL n=%d programs: mean draw = %.6f, sd(ln L) = %.4f %%, dof=%d"
      % (n, math.exp(m), sd * 100, n - 1))

# drop the one radically different program (tanjiro instrument A, cs 2.308)
sub = [r for r in rows if r[1] != "ff29f5c2"]
n2, m2, sd2 = stats([math.log(r[3]) for r in sub])
print("EXCL ff29f5c2 n=%d: mean draw = %.6f, sd(ln L) = %.4f %%, dof=%d"
      % (n2, math.exp(m2), sd2 * 100, n2 - 1))

# code-freeness test: is ln L related to ln cs across these 12 programs?
lncs = [math.log(r[2]) for r in rows]
mx = sum(lncs) / len(lncs)
my = sum(lnL) / len(lnL)
sxy = sum((a - mx) * (b - my) for a, b in zip(lncs, lnL))
sxx = sum((a - mx) ** 2 for a in lncs)
syy = sum((b - my) ** 2 for b in lnL)
r = sxy / math.sqrt(sxx * syy)
print("\ncorr(ln cs, ln L) over 12 distinct programs = %+.3f" % r)
tstat = r * math.sqrt((len(rows) - 2) / (1 - r * r))
print("  t(%d dof) = %+.3f  (|t|>2.23 is 5%% two-sided)" % (len(rows) - 2, tstat))
# same, excluding the outlier program
lncs2 = [math.log(r[2]) for r in sub]
lnL2 = [math.log(r[3]) for r in sub]
mx2 = sum(lncs2) / len(lncs2)
my2 = sum(lnL2) / len(lnL2)
sxy2 = sum((a - mx2) * (b - my2) for a, b in zip(lncs2, lnL2))
sxx2 = sum((a - mx2) ** 2 for a in lncs2)
syy2 = sum((b - my2) ** 2 for b in lnL2)
r2 = sxy2 / math.sqrt(sxx2 * syy2)
print("  excl ff29f5c2 (n=11): corr = %+.3f" % r2)

# chi-square 95% interval for sd, by bisection on the chi2 CDF (no scipy)
def chi2_cdf(x, k):
    # regularized lower incomplete gamma P(k/2, x/2) via series/CF
    a, xx = k / 2.0, x / 2.0
    if xx <= 0:
        return 0.0
    if xx < a + 1:
        term = 1.0 / a
        s = term
        for i in range(1, 500):
            term *= xx / (a + i)
            s += term
            if abs(term) < abs(s) * 1e-15:
                break
        return s * math.exp(-xx + a * math.log(xx) - math.lgamma(a))
    # continued fraction for Q
    tiny = 1e-300
    b = xx + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < 1e-15:
            break
    q = math.exp(-xx + a * math.log(xx) - math.lgamma(a)) * h
    return 1 - q


def chi2_q(p, k):
    lo, hi = 1e-9, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if chi2_cdf(mid, k) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


for label, nn, ss in (("all 12", n, sd), ("excl outlier 11", n2, sd2)):
    k = nn - 1
    lo = ss * math.sqrt(k / chi2_q(0.975, k))
    hi = ss * math.sqrt(k / chi2_q(0.025, k))
    print("95%% CI on sd(ln L), %s: [%.4f, %.4f] %%  (point %.4f %%, %d dof)"
          % (label, lo * 100, hi * 100, ss * 100, k))

print("\nCOMPARISON (all as sd of the draw factor / of ln official):")
for nm, v in (("fern 0.538 (CRS:3509 0.5359)", 0.5359),
              ("my n=5 conditional sd(ln L) 0.5263", 0.5263),
              ("archive n=12 cross-program", sd * 100),
              ("archive n=11", sd2 * 100),
              ("r103 replicate sd(ln cs) 0.2276", 0.2276),
              ("my n=5 sd(ln official) 0.3728", 0.3728)):
    print("  %-34s %.4f %%" % (nm, v))
