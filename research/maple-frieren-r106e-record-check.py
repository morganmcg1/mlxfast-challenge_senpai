#!/usr/bin/env python3
"""R106-E: verify the leaderboard record's session decomposition from the live feed.

Confirms that the top officialScore on the board is reached with a *lower*
master-baseline candidate score than our own tree, i.e. that the record is an
order statistic of the session factor rather than a faster candidate.
"""
import argparse
import json
import math
import os
import subprocess
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
BAND_CS = 2.583106      # the R93 Arm-A replicate-mean cs: "as good a tree as ours"


def fetch():
    req = urllib.request.Request(FEED, headers={
        "Authorization": f"Bearer {os.environ['MLXFAST_API_TOKEN']}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def norm_cdf(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def norm_isf(p):
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if 1.0 - norm_cdf(mid) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def expected_max_normal(n):
    return norm_isf(1.0 - (n - 0.375) / (n + 0.25))


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def note_for(sub_id):
    """Free-text note is the only per-receipt attribution on the shared account."""
    try:
        r = subprocess.run(["mlxfast", "submission-note", sub_id],
                           capture_output=True, text=True, timeout=90)
    except Exception as exc:                       # noqa: BLE001
        return f"<error {exc}>"
    txt = (r.stdout or r.stderr).strip().replace("\n", " | ")
    return txt or "<empty>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes", type=int, default=0,
                    help="fetch attribution notes for the top-N rows by cs")
    ap.add_argument("--out-json")
    args = ap.parse_args()
    data = fetch()
    rows = data if isinstance(data, list) else data.get("submissions", data.get("data"))
    scored = []
    for s in rows:
        m = s.get("officialMetrics") or {}
        os_ = s.get("officialScore")
        if not os_ or not m.get("decode_seconds_per_token"):
            continue
        cs = ((MB_D / m["decode_seconds_per_token"]) ** 0.75 *
              (MB_P / m["prefill_seconds_per_token"]) ** 0.25)
        scored.append({
            "id": s["id"], "commit": (m.get("commit") or "")[:8],
            "created": s.get("createdAt"), "official": os_, "cs": cs,
            "f_pct": (math.log(os_) - math.log(cs)) * 100,
        })
    scored.sort(key=lambda r: -r["official"])
    print(f"scored rows = {len(scored)}")
    print(f"{'rank':>4} {'commit':<9} {'official':>10} {'cs':>10} {'f %':>8}  id")
    for i, r in enumerate(scored[:8], 1):
        print(f"{i:>4} {r['commit']:<9} {r['official']:>10.6f} {r['cs']:>10.6f} "
              f"{r['f_pct']:>8.4f}  {r['id']}")
    print()
    best_cs = sorted(scored, key=lambda r: -r["cs"])[:8]
    print("top by master-baseline candidate score (cs):")
    for i, r in enumerate(best_cs, 1):
        print(f"{i:>4} {r['commit']:<9} {r['official']:>10.6f} {r['cs']:>10.6f} "
              f"{r['f_pct']:>8.4f}  {r['id']}")
    top = scored[0]
    rank_of_top_by_cs = 1 + sum(1 for r in scored if r["cs"] > top["cs"])
    print()
    print(f"record {top['commit']}: official {top['official']:.6f}, "
          f"cs {top['cs']:.6f}, f {top['f_pct']:+.4f} %; "
          f"its cs ranks {rank_of_top_by_cs} of {len(scored)}")

    # Lottery census: the top-cs cohort is the set of trees that are *already*
    # good enough that only a session draw separates them from the record.
    # If that cohort has spent many receipts without taking the record, the
    # per-draw record probability is bounded empirically, not just by a model.
    band = [r for r in scored if r["cs"] >= BAND_CS]
    fs = [r["f_pct"] for r in scored]
    mf = sum(fs) / len(fs)
    sd_f = math.sqrt(sum((x - mf) ** 2 for x in fs) / (len(fs) - 1))
    hits = [r for r in band if r["official"] > top["official"]]
    print()
    print(f"corpus sd(f) = {sd_f:.4f} %  mean {mf:+.4f} %  (n = {len(fs)})")
    print(f"lottery census, cs >= {BAND_CS}: n = {len(band)} receipts, "
          f"max official = {max(r['official'] for r in band):.6f}, "
          f"record-beating draws = {len(hits)}")
    need = [math.log(top["official"] / r["cs"]) * 100 for r in band]
    print(f"  required f to take the record ranges "
          f"{min(need):.4f} % .. {max(need):.4f} % "
          f"(median {sorted(need)[len(need)//2]:.4f} %)")
    bf = [r["f_pct"] for r in band]
    bmean = sum(bf) / len(bf)
    bsd = math.sqrt(sum((x - bmean) ** 2 for x in bf) / (len(bf) - 1))
    fmax = max(bf)
    # If the corpus sd(f) really were available to a top-cs tree, the maximum of
    # len(band) draws would be much larger than what the cohort actually shows.
    p_max = norm_cdf(fmax / sd_f) ** len(band)
    print(f"  observed f in that cohort: max {fmax:+.4f} %, mean {bmean:+.4f} %, "
          f"sd {bsd:.4f} %")
    print(f"  E[max f] over {len(band)} draws at corpus sd = "
          f"{expected_max_normal(len(band)) * sd_f:+.4f} %; "
          f"P(max <= observed | corpus sd) = {p_max:.4f}")
    lncs = [math.log(r["cs"]) * 100 for r in scored]
    corpus_corr = corr(lncs, fs)
    print(f"  corpus corr(ln cs, f) = {corpus_corr:+.4f} "
          f"(within a fixed tree the R93 nulls give -0.79)")
    census = {
        "band_cs": BAND_CS, "n_band": len(band), "n_record_beating": len(hits),
        "band_max_official": max(r["official"] for r in band),
        "required_f_min_pct": min(need), "required_f_max_pct": max(need),
        "required_f_median_pct": sorted(need)[len(need) // 2],
        "band_f_max_pct": fmax, "band_f_mean_pct": bmean, "band_f_sd_pct": bsd,
        "expected_max_f_at_corpus_sd_pct": expected_max_normal(len(band)) * sd_f,
        "p_max_le_observed_given_corpus_sd": p_max,
        "corpus_sd_f_pct": sd_f, "corpus_mean_f_pct": mf,
        "corpus_corr_lncs_f": corpus_corr,
    }

    top_by_cs = sorted(scored, key=lambda x: -x["cs"])
    if args.notes:
        print()
        print(f"attribution notes for the top {args.notes} rows by cs:")
        for i, r in enumerate(top_by_cs[:args.notes], 1):
            r["note"] = note_for(r["id"])
            print(f"{i:>3} {r['commit']:<9} cs {r['cs']:.6f} "
                  f"official {r['official']:.6f} :: {r['note'][:220]}")
    if args.out_json:
        json.dump({"scored": len(scored), "by_official": scored[:12],
                   "by_cs": top_by_cs[:12],
                   "record_cs_rank": rank_of_top_by_cs,
                   "record": scored[0], "census": census},
                  open(args.out_json, "w"), indent=2)
        print(f"\nwrote {args.out_json}")


if __name__ == "__main__":
    main()
