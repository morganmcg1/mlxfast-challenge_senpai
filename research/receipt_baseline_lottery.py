#!/usr/bin/env python3
"""Separate a candidate's real speed change from its paired-baseline lottery draw.

    export MLXFAST_API_TOKEN=...
    python3 research/receipt_baseline_lottery.py

Why this exists
---------------
`officialScore = (baseline_decode/decode)**0.75 * (baseline_prefill/prefill)**0.25`
is a ratio of two independently measured quantities.  The baseline arm runs pinned,
unchangeable reference code on every receipt, so its spread across receipts is pure
measurement noise with a known, directly observable null distribution.

Across 1028 correctness-passing receipts that noise is 1.93% relative on the prefill
axis and 0.248% on the decode axis.  Weighted into the score that is

    sqrt((0.25*1.932)**2 + (0.75*0.248)**2) = 0.518%

of pure baseline noise on every published score, which is larger than most
single-mechanism effects this campaign measures.  Comparing two receipts by
`officialScore` therefore attributes the baseline lottery to the candidate's code.

This script reports, for any receipt:
  1. a log-decomposition of an officialScore gap into a candidate term (real code
     effect) and a baseline term (lottery);
  2. the percentile of its baseline draw inside the observed baseline population;
  3. its "at-median-baseline" score, i.e. the score its code would have received
     against a typical baseline draw, and the lottery premium it actually banked;
  4. an empirical bootstrap of P(beat a target score) holding its candidate speed
     fixed and resampling the 1028 observed baseline pairs.

Attribute mechanisms on candidate seconds (`prefill_seconds_per_token`,
`decode_seconds_per_token`) or on the fixed-normaliser `ns`, never on officialScore.
"""
import argparse
import bisect
import json
import math
import os
import statistics
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "eigenlabs%2Fmlxfast-challenge/submissions")

# Pinned constants from the reporting contract; NOT the session baseline.
NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845


def fetch():
    tok = os.environ["MLXFAST_API_TOKEN"]
    req = urllib.request.Request(FEED, headers={"Authorization": f"Bearer {tok}"})
    raw = json.load(urllib.request.urlopen(req))
    if isinstance(raw, list):
        return raw
    return raw.get("submissions", raw.get("data", []))


def ns_of(prefill, decode):
    """Fixed-normaliser score: depends only on the candidate arm."""
    return ((NORM_DECODE / decode) ** 0.75) * ((NORM_PREFILL / prefill) ** 0.25)


def load():
    rows = {}
    baselines = []
    for sub in fetch():
        met = sub.get("officialMetrics") or sub.get("metrics") or {}
        if not isinstance(met, dict) or not met.get("passed_correctness"):
            continue
        pre = met.get("prefill_seconds_per_token")
        dec = met.get("decode_seconds_per_token")
        bpre = met.get("baseline_prefill_seconds_per_token")
        bdec = met.get("baseline_decode_seconds_per_token")
        score = sub.get("officialScore")
        if not (pre and dec and bpre and bdec and score):
            continue
        sid = sub.get("id", "")
        baselines.append((bpre, bdec))
        rows[sid[:7]] = dict(
            id=sid, day=(sub.get("createdAt") or sub.get("created_at", ""))[:10],
            pre=pre, dec=dec, bpre=bpre, bdec=bdec, score=score,
            ns=ns_of(pre, dec),
            # S = 512-token seed forward, T = marginal one-token step.
            S_ms=512000 * pre, T_ms=1000 * dec - 512000 * pre / 128)
    return rows, baselines


def score_of(pre, dec, bpre, bdec):
    return ((bdec / dec) ** 0.75) * ((bpre / pre) ** 0.25)


def decompose(cand, ref):
    """Split ln(cand.score / ref.score) into candidate and baseline terms."""
    cand_term = (0.75 * math.log(ref["dec"] / cand["dec"])
                 + 0.25 * math.log(ref["pre"] / cand["pre"]))
    base_term = (0.75 * math.log(cand["bdec"] / ref["bdec"])
                 + 0.25 * math.log(cand["bpre"] / ref["bpre"]))
    return cand_term, base_term


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("receipts", nargs="*", default=["c3ce66e", "cdf71fa", "4058d0b"],
                    help="7-char receipt ids; first is treated as the control")
    ap.add_argument("--target", type=float, default=2.552308,
                    help="score to beat in the bootstrap (default: crown)")
    args = ap.parse_args()

    rows, baselines = load()
    bpres = sorted(b for b, _ in baselines)
    mu, sd = statistics.mean(bpres), statistics.stdev(bpres)
    bdecs = [d for _, d in baselines]

    print(f"correctness-passing receipts with both arms: {len(rows)}")
    print("\n=== baseline arm (pinned code on every receipt -> pure noise)")
    print(f"  prefill  mean {mu*1e6:.3f} us  sd {sd*1e6:.3f} ({sd/mu*100:.3f}%)"
          f"  min {bpres[0]*1e6:.3f}  max {bpres[-1]*1e6:.3f}")
    print(f"  decode   mean {statistics.mean(bdecs)*1e3:.5f} ms"
          f"  sd {statistics.stdev(bdecs)*1e3:.5f}"
          f" ({statistics.stdev(bdecs)/statistics.mean(bdecs)*100:.3f}%)")
    weighted = math.hypot(0.25 * sd / mu,
                          0.75 * statistics.stdev(bdecs) / statistics.mean(bdecs))
    print(f"  => baseline noise injected into every officialScore: {weighted*100:.3f}%")

    want = [r for r in args.receipts if r in rows]
    missing = [r for r in args.receipts if r not in rows]
    if missing:
        print(f"\n  not found in feed: {', '.join(missing)}")
    if not want:
        return

    bpre_med, bdec_med = statistics.median(bpres), statistics.median(bdecs)
    print(f"\n=== per receipt (median baseline: prefill {bpre_med*1e6:.3f} us,"
          f" decode {bdec_med*1e3:.5f} ms)")
    hdr = (f"{'id':<8} {'cand_pre':>9} {'cand_dec':>9} {'S_ms':>8} {'T_ms':>7} "
           f"{'ns':>9} {'score':>9} {'at-median':>10} {'lottery':>9} {'base_z':>7} {'pct':>6}")
    print(hdr)
    for rid in want:
        r = rows[rid]
        at_med = score_of(r["pre"], r["dec"], bpre_med, bdec_med)
        pct = bisect.bisect_left(bpres, r["bpre"]) / len(bpres) * 100
        print(f"{rid:<8} {r['pre']*1e6:>9.3f} {r['dec']*1e3:>9.5f} {r['S_ms']:>8.3f} "
              f"{r['T_ms']:>7.4f} {r['ns']:>9.6f} {r['score']:>9.6f} {at_med:>10.6f} "
              f"{(r['score']/at_med-1)*100:>+8.3f}% {(r['bpre']-mu)/sd:>+7.2f} {pct:>5.1f}%")

    ctl = rows[want[0]]
    print(f"\n=== officialScore gaps vs control {want[0]}, decomposed")
    for rid in want[1:]:
        cand_term, base_term = decompose(rows[rid], ctl)
        total = (rows[rid]["score"] / ctl["score"] - 1) * 100
        print(f"  {rid}: total {total:+.3f}%  =  candidate (real code) "
              f"{cand_term*100:+.3f}%  +  baseline (lottery) {base_term*100:+.3f}%")
        print(f"      d ns {(rows[rid]['ns']/ctl['ns']-1)*100:+.3f}%"
              f"   dS {rows[rid]['S_ms']-ctl['S_ms']:+.4f} ms"
              f"   dT {rows[rid]['T_ms']-ctl['T_ms']:+.5f} ms")

    print(f"\n=== bootstrap: P(score > {args.target}) resampling {len(baselines)}"
          " observed baseline draws")
    for rid in want:
        r = rows[rid]
        sims = [score_of(r["pre"], r["dec"], bp, bd) for bp, bd in baselines]
        wins = sum(1 for x in sims if x > args.target)
        prob = wins / len(sims)
        line = (f"  {rid}: E[score] {statistics.mean(sims):.6f}"
                f"  sd {statistics.stdev(sims):.5f}"
                f"  P(beat) {prob*100:.1f}%")
        if prob > 0:
            line += f"  -> expected {1/prob:.0f} receipts"
        print(line)

    # Real candidate-side edge required, so promotion does not rely on the lottery.
    sims = [score_of(ctl["pre"], ctl["dec"], bp, bd) for bp, bd in baselines]
    at_med_ctl = score_of(ctl["pre"], ctl["dec"], bpre_med, bdec_med)
    sd_s = statistics.stdev(sims) / statistics.mean(sims)
    for label, extra in (("50%", 0.0), ("90%", 1.2816)):
        need = (args.target * (1 + extra * sd_s)) / at_med_ctl - 1
        print(f"  candidate-side edge for {label} promotion from {want[0]}:"
              f" {need*100:+.2f}% of score"
              f"  = {-need/0.75*100:+.2f}% decode seconds"
              f"  or {-need/0.25*100:+.2f}% prefill seconds")


if __name__ == "__main__":
    main()
