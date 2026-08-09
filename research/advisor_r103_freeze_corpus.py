#!/usr/bin/env python3
"""Advisor r103: freeze an ENRICHED receipt-corpus snapshot, and inventory every
field the submissions endpoint actually returns.

Two jobs:

1. **Field inventory.** Round-103 arm D (#576) rung 0 asks whether we can tie a
   receipt to a source tree. Nobody has ever dumped the full field set of a
   submission record, so we have been guessing. Print every key seen anywhere in
   the payload, with occupancy counts and one redacted example value, so the
   provenance question is answered from data rather than belief.

2. **Frozen corpus.** The previous snapshot (/tmp/r103-receipts.json) kept only
   id/solver/ts/cs/score/L/status and DISCARDED decode/prefill. But
   `D = 4P + T` needs both, so the whole round-103 residual analysis was
   impossible on that cache. Re-pull keeping D and P (and the baselines), derive
   T exactly, and write a frozen snapshot to research/artifacts/ so every
   analysis in this round is reproducible against identical bytes rather than
   against a live endpoint that keeps moving.

READ-ONLY. Never submits. Never prints the token.

usage: advisor_r103_freeze_corpus.py <out.json>
"""

import collections
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
MB_D = 0.013855009542
MB_P = 0.000372473193

token = os.environ.get("MLXFAST_API_TOKEN")
base = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
cfg_path = pathlib.Path.home() / ".config/mlxfast/config.json"
if not token and cfg_path.exists():
    cfg = json.loads(cfg_path.read_text())
    base = cfg.get("apiBaseUrl", base).rstrip("/")
    token = cfg["token"]
if not token:
    sys.exit("no MLXFAST_API_TOKEN and no ~/.config/mlxfast/config.json")

SECRET = token


def redact(v):
    s = str(v)
    if SECRET and SECRET in s:
        return "<REDACTED>"
    return s[:80]


def get(path):
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Bearer {SECRET}"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def cs_of(dec, pre):
    return (MB_D / dec) ** 0.75 * (MB_P / pre) ** 0.25


def main():
    out = pathlib.Path(sys.argv[1])
    bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
    rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]
    print(f"pulled {len(rows)} raw submission records")

    # ---------- 1. field inventory ----------
    top = collections.Counter()
    top_ex = {}
    met = collections.Counter()
    met_ex = {}
    for r in rows:
        for k, v in r.items():
            if v is None or v == "" or v == {}:
                continue
            top[k] += 1
            top_ex.setdefault(k, redact(v))
        m = r.get("officialMetrics")
        if isinstance(m, dict):
            for k, v in m.items():
                if v is None or v == "":
                    continue
                met[k] += 1
                met_ex.setdefault(k, redact(v))

    print("\n===== TOP-LEVEL submission fields (non-empty occupancy / %d) =====" % len(rows))
    for k, c in top.most_common():
        print(f"  {k:34s} {c:5d}  e.g. {top_ex[k]}")
    print("\n===== officialMetrics fields =====")
    for k, c in met.most_common():
        print(f"  {k:34s} {c:5d}  e.g. {met_ex[k]}")

    # anything that smells like provenance
    print("\n===== provenance-shaped keys (commit/sha/tree/branch/hash/ref/host) =====")
    pat = ("commit", "sha", "tree", "branch", "hash", "ref", "host", "machine", "device", "runner")
    hits = [k for k in list(top) + list(met) if any(p in k.lower() for p in pat)]
    if hits:
        for k in sorted(set(hits)):
            ex = top_ex.get(k, met_ex.get(k))
            n = top.get(k, met.get(k))
            print(f"  {k:34s} {n:5d}  e.g. {ex}")
    else:
        print("  NONE. No commit/tree/host identifier is exposed on submission records.")

    # ---------- 2. frozen enriched corpus ----------
    recs = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        if not isinstance(m, dict):
            continue
        d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if not (d and p and bd and bp):
            continue
        cs = cs_of(d, p)
        score = (bd / d) ** 0.75 * (bp / p) ** 0.25
        D_us = d * 1e6            # decode us/step  (== cand_dec)
        P_us = p * 1e6            # prefill us/token
        recs.append(
            dict(
                id=r["id"][:8],
                solver=r.get("solverUsername"),
                ts=m.get("timestamp") or r.get("createdAt"),
                cs=cs,
                score=score,
                L=score / cs,
                status=r.get("status"),
                # --- the fields the old cache threw away ---
                dec_us_step=D_us,
                pre_us_tok=P_us,
                T_us_step=D_us - 4.0 * P_us,   # exact: D = 4P + T (rule 58)
                base_dec_us_step=bd * 1e6,
                base_pre_us_tok=bp * 1e6,
            )
        )
    recs.sort(key=lambda x: x["ts"] or "")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recs, indent=1, sort_keys=True))
    print(f"\nwrote {len(recs)} usable receipts -> {out}")


if __name__ == "__main__":
    main()
