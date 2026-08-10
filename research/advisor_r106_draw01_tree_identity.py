#!/usr/bin/env python3
"""Decompose the R106-E draw-1 receipt into decode and prefill and ask which
tree it is.

Context
-------
#597 rev4 asked maple-frieren to REPLICATE the tree `4b0e051b` (our best-ever
composite score, cs 2.590559) n = 4 times, to measure the within-tree component
of the submission lottery.  Her first draw came back at cs 2.574073, which is
-0.638 % below `4b0e051b` and only -0.061 % below `origin/main` (`e33efe4e`,
cs 2.575633).  Rule 93.4(f) records the mechanism that would explain it: the
submit wrapper requires `git merge-base --is-ancestor $BASE_SHA HEAD`, and
`origin/main` is NOT an ancestor of `4b0e051b`, so a naive "branch from
`4b0e051b`" recipe forces a merge whose editable files can resolve in
`origin/main`'s favour.

`cs` alone is a composite of two measurements with very different noise, so it
is a blunt discriminator.  This script does the sharper test: it pulls the raw
`decode_seconds_per_token` and `prefill_seconds_per_token` for the draw and for
every anchor tree we have a receipt for, converts to microseconds, and reports
the per-axis z-score of the draw against each anchor.

Why this is stronger than the cs comparison
-------------------------------------------
Decode carries 0.75 of the exponent and has a per-receipt sd of ~0.1839 % in
score terms; prefill carries 0.25 and ~0.1123 %.  Two trees that differ in
decode-side machinery will separate on the decode axis specifically.  If the
draw's decode lands on `origin/main`'s decode and NOT on `4b0e051b`'s, the
wrong-tree hypothesis is confirmed on the axis where the two trees actually
differ, not merely on their aggregate.

This is EVIDENCE FOR A CONVERSATION, not a verdict.  The verdict comes from
maple-frieren's two `git diff --numstat` outputs, which are dispositive where
this is only probabilistic.  Rule 79: the null cell is reported either way.

Isolation
---------
Reads the official submission feed only.  Anchors are restricted to trees this
campaign has itself submitted; no cross-launch comparison is performed and no
foreign PR is consulted.

Usage
-----
    MLXFAST_API_TOKEN=... python3 research/advisor_r106_draw01_tree_identity.py
    ... --marker R106E-DRAW-01 --json /tmp/draw01_identity.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast")

# Score reconstruction, verified to max rel err 3.5e-15 over n = 84 (Rule 93.2).
#   ln cs = X - 0.75 ln cand_dec - 0.25 ln cand_pre
X_CONST = -5.1831677111
MB_D = 0.013855009542  # baseline decode, seconds per step
MB_P = 0.000372473193  # baseline prefill, seconds per token

# Per-receipt channel sigmas expressed in *score* percent (campaign constants).
SD_DECODE_SCORE_PCT = 0.1839
SD_PREFILL_SCORE_PCT = 0.1123

# Within-identical-tree sigma on cs, Rule 93.4(a): pooled over four
# note-declared replicate families, dof = 7.
SD_CS_PCT = 0.1453

# Anchor trees this campaign submitted.  cs values are from the merit table in
# research/CURRENT_RESEARCH_STATE.md; the raw decode/prefill are looked up from
# the feed by matching cs, so a typo here cannot silently invent an anchor.
ANCHORS = {
    "4b0e051b": 2.590559,  # best ever; the tree R106-E is replicating
    "ef055b9b": 2.589321,  # Arm R
    "5a43d329": 2.588750,
    "e1b6e2be": 2.587191,
    "bd33883e": 2.582286,  # merged frontier
    "e33efe4e": 2.575633,  # == origin/main (Rule 89.5)
}
CS_MATCH_TOL = 2e-6


def token() -> str:
    tok = os.environ.get("MLXFAST_API_TOKEN")
    if tok:
        return tok
    cfg = os.path.expanduser("~/.config/mlxfast/config.json")
    if os.path.exists(cfg):
        with open(cfg) as fh:
            return json.load(fh).get("token", "")
    return ""


def get(path: str, tok: str):
    req = urllib.request.Request(BASE + path)
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def composite(dec: float, pre: float) -> float:
    return math.exp(X_CONST - 0.75 * math.log(dec) - 0.25 * math.log(pre))


def session_factor(bdec: float, bpre: float) -> float:
    """f, in percent: the session lottery on the two baseline measurements."""
    return 100.0 * (0.75 * math.log(bdec / MB_D) + 0.25 * math.log(bpre / MB_P))


def rows(subs):
    out = []
    for s in subs:
        m = s.get("officialMetrics") or {}
        dec = m.get("decode_seconds_per_token")
        pre = m.get("prefill_seconds_per_token")
        bdec = m.get("baseline_decode_seconds_per_token")
        bpre = m.get("baseline_prefill_seconds_per_token")
        if not (dec and pre and bdec and bpre):
            continue
        out.append(
            {
                "sha": (s.get("submissionCommitSha") or "")[:12],
                "ts": m.get("timestamp") or s.get("createdAt") or "",
                "note": s.get("note") or "",
                "dec_us": dec * 1e6,
                "pre_us": pre * 1e6,
                "bdec_us": bdec * 1e6,
                "bpre_us": bpre * 1e6,
                "cs": composite(dec, pre),
                "f": session_factor(bdec, bpre),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--marker", default="R106E-DRAW-01",
                    help="substring identifying the draw receipt's note")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    tok = token()
    if not tok:
        print("no MLXFAST_API_TOKEN and no ~/.config/mlxfast/config.json",
              file=sys.stderr)
        return 2

    bench = get("/api/benchmarks/" + urllib.parse.quote(BENCHMARK, safe=""), tok)
    bid = (bench.get("benchmark") or bench)["id"]
    subs = get("/api/benchmarks/%s/submissions" % bid, tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))
    subs = [s for s in subs if s.get("solverUsername") == "morganmcg1"]
    rs = rows(subs)
    print("scored receipts: %d" % len(rs))

    draws = [r for r in rs if args.marker.lower() in r["note"].lower()]
    if not draws:
        print("no receipt matching marker %r" % args.marker)
        return 1

    # Resolve anchors by cs, so a mistyped constant fails loudly.
    resolved = {}
    for name, cs in ANCHORS.items():
        hits = [r for r in rs if abs(r["cs"] - cs) < CS_MATCH_TOL]
        if hits:
            resolved[name] = min(hits, key=lambda r: abs(r["cs"] - cs))
        else:
            print("  ! anchor %s (cs %.6f) has no receipt in the feed" % (name, cs))

    report = {"marker": args.marker, "draws": []}

    for d in draws:
        print("")
        print("=" * 78)
        print("DRAW  %s  %s" % (d["sha"], d["ts"]))
        print("  cs            %.6f" % d["cs"])
        print("  decode        %10.3f us/step" % d["dec_us"])
        print("  prefill       %10.4f us/token" % d["pre_us"])
        print("  baseline dec  %10.3f us/step" % d["bdec_us"])
        print("  baseline pre  %10.4f us/token" % d["bpre_us"])
        print("  f             %+.4f %%" % d["f"])
        print("")
        print("  %-10s %10s %10s | %10s %10s | %9s %9s" %
              ("anchor", "d_cs %", "z_cs", "d_dec %", "z_dec",
               "d_pre %", "z_pre"))
        print("  " + "-" * 74)
        entry = {k: d[k] for k in ("sha", "ts", "cs", "dec_us", "pre_us", "f")}
        entry["vs"] = {}
        for name, a in sorted(resolved.items(), key=lambda kv: -kv[1]["cs"]):
            d_cs = 100.0 * math.log(d["cs"] / a["cs"])
            z_cs = d_cs / SD_CS_PCT
            # A decode ratio moves the score by 0.75x its log-ratio.
            d_dec = 100.0 * math.log(d["dec_us"] / a["dec_us"])
            z_dec = (0.75 * -d_dec) / SD_DECODE_SCORE_PCT
            d_pre = 100.0 * math.log(d["pre_us"] / a["pre_us"])
            z_pre = (0.25 * -d_pre) / SD_PREFILL_SCORE_PCT
            print("  %-10s %+10.4f %+10.2f | %+10.4f %+10.2f | %+9.4f %+9.2f" %
                  (name, d_cs, z_cs, d_dec, z_dec, d_pre, z_pre))
            entry["vs"][name] = {
                "anchor_cs": a["cs"], "anchor_dec_us": a["dec_us"],
                "anchor_pre_us": a["pre_us"],
                "d_cs_pct": d_cs, "z_cs": z_cs,
                "d_dec_pct": d_dec, "z_dec": z_dec,
                "d_pre_pct": d_pre, "z_pre": z_pre,
            }

        # Likelihood ratio between the two competing tree identities, on cs.
        if "4b0e051b" in resolved and "e33efe4e" in resolved:
            z1 = entry["vs"]["4b0e051b"]["z_cs"]
            z0 = entry["vs"]["e33efe4e"]["z_cs"]
            lr = math.exp(0.5 * (z1 * z1 - z0 * z0))
            print("")
            print("  Gaussian LR (archived surface was origin/main vs 4b0e051b)"
                  " on cs: %.1f : 1" % lr)
            entry["lr_main_over_4b0e"] = lr
            # Same test on the decode axis alone, which is where the two trees
            # actually differ.  Reported separately: if the two axes disagree,
            # neither hypothesis is clean and the diff outputs must decide.
            zd1 = entry["vs"]["4b0e051b"]["z_dec"]
            zd0 = entry["vs"]["e33efe4e"]["z_dec"]
            lrd = math.exp(0.5 * (zd1 * zd1 - zd0 * zd0))
            print("  Gaussian LR on the DECODE axis alone:              "
                  " %.1f : 1" % lrd)
            entry["lr_main_over_4b0e_decode"] = lrd
            if (lr > 10) != (lrd > 10):
                print("  ! the cs axis and the decode axis DISAGREE; treat both"
                      " as inconclusive")
        report["draws"].append(entry)

    print("")
    print("This is probabilistic evidence only.  The dispositive test is the "
          "pair of\n`git diff --numstat` outputs requested in #597 "
          "(Rule 93.4(f)).")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=1)
        print("wrote %s" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
