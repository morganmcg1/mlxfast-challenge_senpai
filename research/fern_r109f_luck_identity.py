#!/usr/bin/env python3
"""READ-ONLY: is the ``draw'' term of published scores EXACTLY the harness's
re-measurement of the reference implementation?

Background.  Earlier work in this campaign decomposed every scored public
receipt as

    published = normalized x draw,
    normalized = (D0/candidate_decode)^0.75 x (P0/candidate_prefill)^0.25

with fixed constants D0/P0, and measured sd(draw) = 0.538 % over 1280 rows.
That estimator was criticised (ledger section 10.3) on the grounds that no
commit sha is ever scored twice, so cross-row dispersion could conflate code
differences with luck.  This script settles it by testing an algebraic identity
instead of a statistic.

If the harness computes speedups against the baseline it re-measures on every
run, i.e.

    decode_speedup  = baseline_decode  / candidate_decode
    prefill_speedup = baseline_prefill / candidate_prefill
    officialScore   = decode_speedup^0.75 x prefill_speedup^0.25

then substituting gives, with no statistics at all,

    draw = published / normalized
         = (baseline_decode/D0)^0.75 x (baseline_prefill/P0)^0.25

i.e. the draw term depends ONLY on the two re-measured baseline numbers and not
at all on the candidate's code.  Then cross-row draw dispersion is pure jitter
by construction, the 0.538 % is unbiased, and the luck term is fully observable
from the receipt.

Usage: python3 research/fern_r109f_luck_identity.py <submissions.json>
"""
import json
import math
import statistics
import sys

D0 = 0.01385621216015625
P0 = 0.00036751938916015626


def norm_keys(m):
    return {k.lower().replace("-", "_"): v for k, v in m.items()}


def pick(d, *cands):
    for c in cands:
        v = d.get(c)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def main():
    path = sys.argv[1]
    with open(path) as fh:
        blob = json.load(fh)
    rows = blob if isinstance(blob, list) else (
        blob.get("submissions") or blob.get("items") or blob.get("data") or [])

    keyseen = {}
    recs = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        score = r.get("officialScore")
        m = r.get("officialMetrics")
        if not isinstance(score, (int, float)) or not isinstance(m, dict):
            continue
        d = norm_keys(m)
        for k in d:
            keyseen[k] = keyseen.get(k, 0) + 1
        cd = pick(d, "candidate_decode_seconds_per_token", "decode_seconds_per_token")
        cp = pick(d, "candidate_prefill_seconds_per_token", "prefill_seconds_per_token")
        bd = pick(d, "baseline_decode_seconds_per_token")
        bp = pick(d, "baseline_prefill_seconds_per_token")
        ds = pick(d, "decode_speedup")
        ps = pick(d, "prefill_speedup")
        if None in (cd, cp, bd, bp, ds, ps):
            continue
        if len(sys.argv) > 2 and float(score) < float(sys.argv[2]):
            continue
        # Selecting on the CODE side (normalized) instead of on the outcome
        # (published) avoids collider bias when estimating the covariance
        # between the code factor and the luck factor.
        if len(sys.argv) > 3:
            normalized = (D0 / cd) ** 0.75 * (P0 / cp) ** 0.25
            if normalized < float(sys.argv[3]):
                continue
        recs.append((float(score), cd, cp, bd, bp, ds, ps))

    print("rows total            :", len(rows))
    print("rows usable           :", len(recs))
    print("metric keys (top 24)  :")
    for k, n in sorted(keyseen.items(), key=lambda kv: -kv[1])[:24]:
        print("   %-46s %d" % (k, n))
    if not recs:
        return 1

    def maxrel(pairs):
        return max(abs(a - b) / abs(b) for a, b in pairs)

    print()
    print("IDENTITY 1  decode_speedup  == baseline_decode/candidate_decode")
    print("   max rel err :", "%.3e" % maxrel([(ds, bd / cd) for _, cd, _, bd, _, ds, _ in recs]))
    print("IDENTITY 2  prefill_speedup == baseline_prefill/candidate_prefill")
    print("   max rel err :", "%.3e" % maxrel([(ps, bp / cp) for _, _, cp, _, bp, _, ps in recs]))
    print("IDENTITY 3  officialScore   == ds^0.75 * ps^0.25")
    print("   max rel err :", "%.3e" % maxrel(
        [(sc, ds ** 0.75 * ps ** 0.25) for sc, _, _, _, _, ds, ps in recs]))

    draws, preds = [], []
    for sc, cd, cp, bd, bp, ds, ps in recs:
        normalized = (D0 / cd) ** 0.75 * (P0 / cp) ** 0.25
        draws.append(sc / normalized)
        preds.append((bd / D0) ** 0.75 * (bp / P0) ** 0.25)
    print("IDENTITY 4  draw = published/normalized == (bd/D0)^.75 * (bp/P0)^.25")
    print("   max rel err :", "%.3e" % maxrel(list(zip(draws, preds))))

    ld = [math.log(x) for x in draws]
    print()
    print("draw distribution (n=%d)" % len(draws))
    print("   median      : %.6f" % statistics.median(draws))
    print("   rel sd      : %.4f %%" % (100 * statistics.stdev(ld)))
    bdv = [math.log(bd / D0) for _, _, _, bd, _, _, _ in recs]
    bpv = [math.log(bp / P0) for _, _, _, _, bp, _, _ in recs]
    sd_bd = statistics.stdev(bdv)
    sd_bp = statistics.stdev(bpv)
    try:
        rho = statistics.correlation(bdv, bpv)
    except Exception:
        rho = float("nan")
    var = (0.75 * sd_bd) ** 2 + (0.25 * sd_bp) ** 2 + \
        2 * 0.75 * 0.25 * rho * sd_bd * sd_bp
    print("   baseline decode  rel sd : %.4f %%" % (100 * sd_bd))
    print("   baseline prefill rel sd : %.4f %%" % (100 * sd_bp))
    print("   corr(log bd, log bp)    : %+.4f" % rho)
    print("   propagated draw sd      : %.4f %%" % (100 * math.sqrt(var)))
    print("   variance share decode   : %.1f %%" % (
        100 * (0.75 * sd_bd) ** 2 / var))
    print("   variance share prefill  : %.1f %%" % (
        100 * (0.25 * sd_bp) ** 2 / var))

    # ---- does the same-run ratio cancel the baseline jitter? -------------
    # The score is a ratio of two numbers measured back-to-back in the SAME
    # run.  If host state is common-mode, sd(log speedup) must come out much
    # SMALLER than sd(log baseline), even across rows where code differs.
    lcd = [math.log(cd) for _, cd, _, _, _, _, _ in recs]
    lcp = [math.log(cp) for _, _, cp, _, _, _, _ in recs]
    lds = [math.log(ds) for _, _, _, _, _, ds, _ in recs]
    lps = [math.log(ps) for _, _, _, _, _, _, ps in recs]
    lpub = [math.log(sc) for sc, _, _, _, _, _, _ in recs]
    lnorm = [lp - l for lp, l in zip(lpub, ld)]

    def cor(a, b):
        try:
            return statistics.correlation(a, b)
        except Exception:
            return float("nan")

    print()
    print("COMMON-MODE TEST (cross-row, n=%d)" % len(recs))
    print("   sd log baseline_prefill  : %.4f %%" % (100 * sd_bp))
    print("   sd log candidate_prefill : %.4f %%" % (100 * statistics.stdev(lcp)))
    print("   sd log prefill_speedup   : %.4f %%   <-- ratio" % (100 * statistics.stdev(lps)))
    print("   corr(log bp, log cp)     : %+.4f" % cor(lbp_ := bpv, lcp))
    print("   sd log baseline_decode   : %.4f %%" % (100 * sd_bd))
    print("   sd log candidate_decode  : %.4f %%" % (100 * statistics.stdev(lcd)))
    print("   sd log decode_speedup    : %.4f %%   <-- ratio" % (100 * statistics.stdev(lds)))
    print("   corr(log bd, log cd)     : %+.4f" % cor(bdv, lcd))
    print()
    print("   sd log published         : %.4f %%" % (100 * statistics.stdev(lpub)))
    print("   sd log normalized        : %.4f %%" % (100 * statistics.stdev(lnorm)))
    print("   sd log draw              : %.4f %%" % (100 * statistics.stdev(ld)))
    print("   corr(log normalized, log draw) : %+.4f" % cor(lnorm, ld))
    indep = math.sqrt(statistics.stdev(lnorm) ** 2 + statistics.stdev(ld) ** 2)
    print("   independent prediction for sd log published : %.4f %%" % (100 * indep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
