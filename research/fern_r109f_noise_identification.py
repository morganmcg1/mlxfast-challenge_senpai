#!/usr/bin/env python3
"""SUPERSEDED / HEADLINE REFUTED -- kept only as a record of the error.

    DO NOT QUOTE THIS SCRIPT'S OUTPUT.

It prints "IDENTIFIED per-shot luck sd = 1.980 % (all rows) / 0.845 % (48 h)"
and hence "P(one shot clears bar) 23.45 % Gaussian / 35.18 % fat-tail, 8 shots
-> 96.9 %".  All of those numbers are WRONG, too large by roughly an order of
magnitude in probability.  Two bugs:

  1. it assumes the CANDIDATE measurement noise equals the BASELINE measurement
     noise.  Measured directly, candidate-side dispersion over 175 code-selected
     near-best rows is <= 0.2915 %, against a baseline-prefill dispersion of
     1.93 %.  The assumption roughly doubles the noise.
  2. having doubled it, the cross-covariance term is then added with the wrong
     sign convention, inflating the total further instead of shrinking it.

The script's own sanity check prints IMPOSSIBLE and that was ignored.

Correct treatment, with the luck term recovered as an exact identity rather than
an assumption: see `research/fern_r109f_luck_identity.py` and the write-up
`research/fern-r109f-luck-term-identified.md`.  Per-shot published sigma is
0.55-0.60 %; per-shot P(clear bar) is ~1.5-2 %; an 8-shot campaign is worth
~12-15 %, not 97 %.

--- original docstring below ---

READ-ONLY: identify the per-shot LUCK term of the score, without repeats.

Setting.  The score is exactly

    officialScore = (bd/cd)**0.75 * (bp/cp)**0.25

with bd,bp the harness's measured BASELINE seconds/token and cd,cp the
CANDIDATE's, all four reported in officialMetrics on every row.  Write logs:

    log bd = B_d + f_d      log cd = C_d(code) + e_d
    log bp = B_p + f_p      log cp = C_p(code) + e_p

f,e are measurement noise; C(code) is the thing we are actually trying to
improve.  No commit was ever scored twice, so the noise is not identifiable
from repeats.  Two facts rescue it:

  1. the baseline is the SAME program on every row, so sd(log b) IS the
     harness's noise for that quantity -- 0.245 % decode, 1.963 % prefill,
     stationary and white (fern_r109f_baseline_timing_edge.py);
  2. Cov(log b, log c) across rows equals Cov(f, e) exactly, because the code
     term C is independent of the baseline's measurement noise.  So the
     COMMON-MODE part of the noise is identifiable even though the candidate's
     own noise variance is buried under code diversity.

That matters a lot.  The score depends on log b - log c, so

    Var(noise in log speedup) = Var(f) + Var(e) - 2 Cov(f, e).

If the harness measures baseline and candidate back to back on one machine in
one session, thermal/DVFS/neighbour state is shared, Cov(f,e) > 0, and the
ratio is far quieter than either timing.  If Cov(f,e) ~ 0 the noise adds.
Assuming Var(e) ~ Var(f) (same quantity, same harness, same box) gives

    sd(noise in log speedup) = sqrt(2 (1 - rho)) * sd(log b),  rho = Cov(f,e)/Var(f)

which is what this script measures, for both channels plus their cross term,
and then turns into P(one shot beats the bar) for our tree.

Cross-check available: the dispersion of our own 104 scored rows is 0.538 %,
and that number CONTAINS code differences, so any honest luck estimate must
come out at or below it.  The naive rho=0 answer is 0.741 %, i.e. already
impossible -- direct evidence that rho > 0.

Usage: python3 research/fern_r109f_noise_identification.py <queue.json> [...]
"""
import datetime as dt
import json
import math
import statistics
import sys

BD = "baseline_decode_seconds_per_token"
BP = "baseline_prefill_seconds_per_token"
CD = "decode_seconds_per_token"
CP = "prefill_seconds_per_token"
W_D, W_P = 0.75, 0.25

BAR = 2.61955310948
OUR_TREE_MEDIAN = 2.582263      # median normalized draw of our best tree
OUR_ROW_DISPERSION = 0.00538    # sd of our 104 scored rows (code + luck)
TAIL_INFLATION = 1.5            # empirical/Gaussian tail ratio seen at z~2.34


def load(paths):
    seen, rows = set(), []
    for p in paths:
        doc = json.load(open(p))
        for r in doc.get("submissions", doc):
            i = r.get("id")
            if i not in seen:
                seen.add(i)
                rows.append(r)
    return rows


def parse(ts):
    try:
        return dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def quad(rows, hours=None):
    """[(log bd, log cd, log bp, log cp)] for rows with all four timings."""
    now = None
    stamps = [parse(r.get("updatedAt")) for r in rows]
    stamps = [s for s in stamps if s]
    if stamps:
        now = max(stamps)
    out = []
    for r in rows:
        m = r.get("officialMetrics")
        if not isinstance(m, dict):
            continue
        vals = [m.get(k) for k in (BD, CD, BP, CP)]
        if not all(isinstance(v, (int, float)) and v > 0 for v in vals):
            continue
        if hours is not None and now is not None:
            t = parse(r.get("updatedAt"))
            if t is None or t < now - dt.timedelta(hours=hours):
                continue
        out.append(tuple(math.log(float(v)) for v in vals))
    return out


def cov(a, b):
    n = len(a)
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)


def corr(a, b):
    va, vb = cov(a, a), cov(b, b)
    return cov(a, b) / math.sqrt(va * vb) if va > 0 and vb > 0 else float("nan")


def phi(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def analyse(q, label):
    lbd = [x[0] for x in q]
    lcd = [x[1] for x in q]
    lbp = [x[2] for x in q]
    lcp = [x[3] for x in q]
    n = len(q)
    print(f"\n#################### {label}  (n={n})")
    if n < 30:
        print("  too few rows")
        return None

    var_fd, var_fp = cov(lbd, lbd), cov(lbp, lbp)
    sd_fd, sd_fp = math.sqrt(var_fd), math.sqrt(var_fp)
    print(f"  harness noise from the baseline itself: "
          f"decode {100*sd_fd:.3f}%  prefill {100*sd_fp:.3f}%")
    print(f"  candidate dispersion (code + noise):    "
          f"decode {100*math.sqrt(cov(lcd,lcd)):.3f}%  "
          f"prefill {100*math.sqrt(cov(lcp,lcp)):.3f}%")

    # --- common mode: Cov(log b, log c) == Cov(f, e) ---
    cov_d, cov_p = cov(lbd, lcd), cov(lbp, lcp)
    rho_d = cov_d / var_fd
    rho_p = cov_p / var_fp
    print(f"\n  == common-mode fraction rho = Cov(f,e)/Var(f) ==")
    print(f"  decode : Cov={cov_d:+.3e}  rho={rho_d:+.3f}  "
          f"(raw corr with candidate {corr(lbd,lcd):+.3f})")
    print(f"  prefill: Cov={cov_p:+.3e}  rho={rho_p:+.3f}  "
          f"(raw corr with candidate {corr(lbp,lcp):+.3f})")
    print("  rho ~ 0 -> noises add; rho -> 1 -> the ratio cancels the noise")

    # --- noise variance of each log speedup, Var(f)+Var(e)-2Cov, Var(e)~Var(f)
    v_spd_d = max(0.0, 2 * var_fd * (1 - rho_d))
    v_spd_p = max(0.0, 2 * var_fp * (1 - rho_p))

    # --- cross term between the two speedups' noise ---
    # Cov(f_d-e_d, f_p-e_p) = Cov(f_d,f_p)+Cov(e_d,e_p)-Cov(f_d,e_p)-Cov(e_d,f_p)
    # with Cov(e_d,e_p) ~ Cov(f_d,f_p) by the same equal-noise assumption.
    c_ff = cov(lbd, lbp)
    c_fe = cov(lbd, lcp)
    c_ef = cov(lcd, lbp)
    c_cross = 2 * c_ff - c_fe - c_ef

    v_score = (W_D ** 2) * v_spd_d + (W_P ** 2) * v_spd_p + \
        2 * W_D * W_P * c_cross
    v_score = max(0.0, v_score)
    sd_score = math.sqrt(v_score)
    naive = math.sqrt((W_D * math.sqrt(2) * sd_fd) ** 2 +
                      (W_P * math.sqrt(2) * sd_fp) ** 2)
    print(f"\n  == per-shot score noise ==")
    print(f"  decode  channel contributes {100*W_D*math.sqrt(v_spd_d):.3f}%")
    print(f"  prefill channel contributes {100*W_P*math.sqrt(v_spd_p):.3f}%")
    print(f"  cross term 2*wd*wp*Cov = {2*W_D*W_P*c_cross:+.3e}")
    print(f"  IDENTIFIED per-shot luck sd = {100*sd_score:.3f}%")
    print(f"  naive rho=0 answer          = {100*naive:.3f}%  "
          f"(ratio {naive/sd_score if sd_score else float('nan'):.2f}x)")
    print(f"  sanity ceiling: our own scored rows disperse "
          f"{100*OUR_ROW_DISPERSION:.3f}% INCLUDING code differences")
    verdict = "CONSISTENT" if sd_score <= OUR_ROW_DISPERSION * 1.05 \
        else "IMPOSSIBLE -> rho must be larger / Var(e) < Var(f)"
    print(f"  -> {verdict}")
    return sd_score


def crown(sd_score):
    need = BAR / OUR_TREE_MEDIAN - 1.0
    z = math.log1p(need) / sd_score
    p_g = phi(z)
    p_t = min(1.0, p_g * TAIL_INFLATION)
    print(f"\n== crown probability from our best tree "
          f"(median draw {OUR_TREE_MEDIAN}, bar {BAR}) ==")
    print(f"  gap to close: {100*need:.3f}%   z = {z:.3f}")
    print(f"  P(one shot clears the bar): gaussian {100*p_g:.2f}%   "
          f"with the empirical 1.5x tail {100*p_t:.2f}%")
    print(f"  {'shots':>6} {'P(crown) gauss':>16} {'P(crown) fat-tail':>18}")
    for k in range(1, 9):
        print(f"  {k:>6} {100*(1-(1-p_g)**k):>15.2f}% "
              f"{100*(1-(1-p_t)**k):>17.2f}%")
    print("  (independent shots: justified -- the baseline noise is white,"
          " lag1 autocorr -0.005)")


def main(paths):
    rows = load(paths)
    print(f"rows loaded: {len(rows)}")
    full = analyse(quad(rows), "all rows with four timings")
    rec = analyse(quad(rows, hours=48), "last 48h only")
    use = full
    if use:
        crown(use)
    if rec and full:
        print(f"\nstability check: all-rows {100*full:.3f}% vs "
              f"48h {100*rec:.3f}%")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
