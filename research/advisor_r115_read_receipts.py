#!/usr/bin/env python3
"""r115 — refresh the receipt feed and read named receipts on RAW legs.

Per section 0P.15 the official score is the *worst* instrument we own: pairing
against the baseline arm multiplies decode noise by 1.83x and prefill noise by
9.28x.  So every read here is on the RAW candidate legs
(``decode_seconds_per_token`` / ``prefill_seconds_per_token``) and the score is
printed only for the record.

Usage::

    python3 research/advisor_r115_read_receipts.py <id-prefix> [<id-prefix> ...]

With no arguments it prints every morganmcg1 receipt from the last 36 hours.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
CACHE = "/tmp/mlxfast_subs_r115.json"

# Section 0P.15 pooled within-family sds, in percent of the arm's own mean.
# r116 CORRECTION -- L-DECODE-SD-IS-HETEROGENEOUS (section 0P.16).
#
# The pooled 0.1440 % decode sd of section 0P.15 is NOT usable for a single
# receipt.  Per-family decode sds span 0.0145 % (H, the advisor-HEAD class) to
# 0.3064 % (R) to 0.3036 % (atlasv3), and the pooled figure is dragged down by
# H, whose four receipts landed within 0.03 % of one another -- an anomalously
# quiet window, not the typical one.
#
# The proof is our own null.  Receipt 0531544 is a comment-only nonce replay of
# ed40f3e: byte-equivalent, semantically identical.  It drew cand decode
# -0.5025 % against the HEAD-class mean, i.e. z = -3.49 at sd 0.1440 %.  A tree
# with no code change cannot be 3.5 sigma faster.  The sd is wrong, not the tree.
#
# So: read a single decode receipt at sd 0.30 %.  Prefill shows no such blow-up
# (family sds 0.0553 %-0.1297 %, all below the pooled 0.2033 %), so the pooled
# prefill sd stays and remains conservative.
SD_DECODE_PCT = 0.30
SD_PREFILL_PCT = 0.2033
SD_SCORE_PCT = 0.4938

# Retained for the record: the section 0P.15 pooled decode figure, valid only
# for multi-draw within-family contrasts, never for a single receipt.
SD_DECODE_PCT_POOLED_0P15 = 0.1440

# Maple HEAD executable class, n = 4 (section 0P.14 / 0P.15).
HEAD_CLASS = {
    "c1c0ba2": (2.56974410819947, 4.932374, 187.6946),
    "2771067": (2.59380735131190, 4.931369, 188.1609),
    "8858427": (2.59576526895414, 4.932643, 187.6487),
    "2aedeb8": (2.60026627118063, 4.931208, 187.9871),
}
HEAD_DECODE_MS = sum(v[1] for v in HEAD_CLASS.values()) / len(HEAD_CLASS)
HEAD_PREFILL_US = sum(v[2] for v in HEAD_CLASS.values()) / len(HEAD_CLASS)
HEAD_SCORE = sum(v[0] for v in HEAD_CLASS.values()) / len(HEAD_CLASS)


def fetch() -> list[dict]:
    token = os.environ.get("MLXFAST_API_TOKEN")
    if not token:
        raise SystemExit("MLXFAST_API_TOKEN is not set")
    base = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast").rstrip("/")
    url = f"{base}/api/benchmarks/{urllib.parse.quote(BENCH, safe='')}/submissions"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.load(resp)
    rows = payload["submissions"] if isinstance(payload, dict) else payload
    with open(CACHE, "w") as fh:
        json.dump(rows, fh)
    return rows


def metrics(row: dict) -> dict:
    m = row.get("officialMetrics")
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except Exception:
            return {}
    return m or {}


def legs(row: dict):
    m = metrics(row)
    try:
        return (
            float(m["decode_seconds_per_token"]) * 1e3,
            float(m["prefill_seconds_per_token"]) * 1e6,
            float(m["baseline_decode_seconds_per_token"]) * 1e3,
            float(m["baseline_prefill_seconds_per_token"]) * 1e6,
        )
    except (KeyError, TypeError, ValueError):
        return None


def sigma_line(label: str, value: float, ref: float, sd_pct: float, lower_is_better: bool = True) -> str:
    delta_pct = 100.0 * (value - ref) / ref
    # se of (one draw - mean of four) with a common within-family sd
    se_pct = sd_pct * (1.0 + 1.0 / 4.0) ** 0.5
    sigma = delta_pct / se_pct
    verdict = "FASTER" if (delta_pct < 0) == lower_is_better else "slower"
    if abs(sigma) < 2.0:
        verdict = "null (|z|<2)"
    return (f"  {label:<10} {value:12.6f}  vs HEAD {ref:12.6f}  "
            f"delta {delta_pct:+7.4f}%  z {sigma:+6.2f}  {verdict}")


def main() -> int:
    rows = fetch()
    wanted = [a.lower() for a in sys.argv[1:]]
    if wanted:
        sel = [r for r in rows if any(str(r.get("id", "")).lower().startswith(w) for w in wanted)]
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
        sel = []
        for r in rows:
            if r.get("solverUsername") != "morganmcg1":
                continue
            ts = r.get("createdAt")
            try:
                when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except Exception:
                continue
            if when >= cutoff:
                sel.append(r)
    sel.sort(key=lambda r: str(r.get("createdAt", "")))

    print(f"receipts in feed: {len(rows)}   selected: {len(sel)}")
    print(f"HEAD class n=4: score {HEAD_SCORE:.8f}  decode {HEAD_DECODE_MS:.6f} ms  "
          f"prefill {HEAD_PREFILL_US:.4f} us")
    print()
    for r in sel:
        rid = str(r.get("id", ""))[:7]
        lg = legs(r)
        print(f"== {rid}  {r.get('createdAt')}  status={r.get('status')}  "
              f"score={r.get('officialScore')}")
        if not lg:
            print("   (no paired metrics yet)")
            print()
            continue
        cd, cp, bd, bp = lg
        print(f"   raw legs: cand decode {cd:.6f} ms | cand prefill {cp:.4f} us | "
              f"base decode {bd:.6f} ms | base prefill {bp:.4f} us")
        print(sigma_line("decode", cd, HEAD_DECODE_MS, SD_DECODE_PCT))
        print(sigma_line("prefill", cp, HEAD_PREFILL_US, SD_PREFILL_PCT))
        sc = r.get("officialScore")
        if isinstance(sc, (int, float)):
            print(sigma_line("score", float(sc), HEAD_SCORE, SD_SCORE_PCT, lower_is_better=False))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
