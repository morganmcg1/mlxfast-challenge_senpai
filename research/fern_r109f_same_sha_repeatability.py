#!/usr/bin/env python3
"""fern R109-F: how repeatable is the ranked *candidate* decode leg?

Why this exists
---------------
Two contradictory readings of the same receipt set were live:

  * `pkg-t1` (074f47e4) and `pkg-t2` (04e8bf3c) are the same executable and
    measured 4932.4 / 4932.6 us candidate decode - 0.0054 % apart.  Read as
    instrument noise that would make the candidate leg a ~0.3 us instrument.
  * morganmcg1's 2026-08-10 03:42-11:05 rapid-fire shots ranged 4890.7-4933.8
    us, a 43 us spread, which read as instrument noise instead would make every
    "package X is faster than package Y" claim in that range meaningless.

Only one of those can be right, and the arbiter is *repeated submissions of a
byte-identical commit*: group every full-leg receipt by `submissionCommitSha`,
keep the shas submitted more than once, and look at the within-sha spread.
Within-sha spread is pure instrument (same code, same host, different moment);
between-sha spread is instrument + code.

Usage:
    python3 research/fern_r109f_same_sha_repeatability.py [receipts.json]
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs_p4.json"

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626


def normalized(dec: float, pf: float) -> float:
    return (REF_D / dec) ** 0.75 * (REF_P / pf) ** 0.25


def main() -> None:
    with open(PATH) as fh:
        rows = json.load(fh)["submissions"]

    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        m = r.get("officialMetrics") or {}
        dec = m.get("decode_seconds_per_token")
        pf = m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        sha = r.get("submissionCommitSha")
        if not (dec and pf and bd and bp and sha):
            continue
        if not m.get("passed_correctness"):
            continue
        groups[sha].append({
            "id": r["id"][:8],
            "solver": r["solverUsername"],
            "created": (r.get("createdAt") or "")[:19],
            "dec": dec * 1e6,
            "pf": pf * 1e6,
            "bdec": bd * 1e6,
            "bpf": bp * 1e6,
            "norm": normalized(dec, pf),
            "published": r.get("officialScore"),
        })

    repeats = {s: v for s, v in groups.items() if len(v) >= 2}
    for v in repeats.values():
        v.sort(key=lambda x: x["created"])

    print("=" * 104)
    print("fern R109-F: within-commit repeatability of the ranked legs")
    print("  source = %s" % PATH)
    print("  full-leg correct receipts     : %d" % sum(len(v) for v in groups.values()))
    print("  distinct submissionCommitSha  : %d" % len(groups))
    print("  shas submitted >= 2 times     : %d" % len(repeats))
    print("=" * 104)

    rel_dec, rel_pf, rel_norm, rel_bdec, rel_bpf, rel_pub = [], [], [], [], [], []
    print("%-11s %3s %-13s %9s %9s %9s %9s %11s" % (
        "sha", "n", "solver", "dec_spr%", "pf_spr%", "bdec_spr%", "bpf_spr%",
        "norm_spr%"))
    print("-" * 104)
    for sha, v in sorted(repeats.items(), key=lambda kv: -len(kv[1])):
        def spread(key: str) -> float:
            xs = [x[key] for x in v]
            return 100.0 * (max(xs) - min(xs)) / statistics.mean(xs)

        d, p, bd, bp, nz = (spread("dec"), spread("pf"), spread("bdec"),
                            spread("bpf"), spread("norm"))
        rel_dec.append(d)
        rel_pf.append(p)
        rel_bdec.append(bd)
        rel_bpf.append(bp)
        rel_norm.append(nz)
        pubs = [x["published"] for x in v if x["published"]]
        if len(pubs) >= 2:
            rel_pub.append(100.0 * (max(pubs) - min(pubs)) / statistics.mean(pubs))
        print("%-11s %3d %-13s %9.4f %9.4f %9.4f %9.4f %11.4f" % (
            sha[:10], len(v), v[0]["solver"][:13], d, p, bd, bp, nz))

    def stat(name: str, xs: list) -> None:
        if not xs:
            print("  %-24s n=0" % name)
            return
        print("  %-24s n=%3d  min %8.4f  med %8.4f  mean %8.4f  max %8.4f" % (
            name, len(xs), min(xs), statistics.median(xs),
            statistics.fmean(xs), max(xs)))

    print()
    print("within-sha relative spread (max-min)/mean, in percent")
    print("-" * 104)
    stat("candidate decode", rel_dec)
    stat("candidate prefill", rel_pf)
    stat("baseline decode", rel_bdec)
    stat("baseline prefill", rel_bpf)
    stat("normalized score", rel_norm)
    stat("published score", rel_pub)

    # pooled within-sha standard deviation of candidate decode, in us
    pooled_num = 0.0
    pooled_dof = 0
    for v in repeats.values():
        xs = [x["dec"] for x in v]
        if len(xs) < 2:
            continue
        m = statistics.fmean(xs)
        pooled_num += sum((x - m) ** 2 for x in xs)
        pooled_dof += len(xs) - 1
    if pooled_dof:
        sd = (pooled_num / pooled_dof) ** 0.5
        print()
        print("pooled within-sha SD of candidate decode : %.2f us  (dof=%d)"
              % (sd, pooled_dof))
        print("  => a %.1f us gap between two different packages is %.1f sigma"
              % (41.7, 41.7 / sd))

    print()
    print("per-receipt detail for the repeated shas")
    print("-" * 104)
    for sha, v in sorted(repeats.items(), key=lambda kv: -len(kv[1])):
        print("%s  (%s, n=%d)" % (sha[:12], v[0]["solver"], len(v)))
        for x in v:
            print("    %s %s  dec %8.1f  pf %7.2f  bdec %8.1f  bpf %7.2f  "
                  "norm %.6f" % (x["id"], x["created"], x["dec"], x["pf"],
                                 x["bdec"], x["bpf"], x["norm"]))


if __name__ == "__main__":
    main()
