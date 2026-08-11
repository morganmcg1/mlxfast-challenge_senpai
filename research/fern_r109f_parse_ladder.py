#!/usr/bin/env python3
"""Parse the score JSON embedded in each --local-submit ladder log.

The ladder runner copied the wrong filenames (score.local-submit.json instead of
score.json), so the authoritative record of each draw is the JSON block the
harness echoes into the per-draw log. This tool recovers it, recomputes the
official normalisation constant from the raw legs, and reports dispersion.

Usage: fern_r109f_parse_ladder.py <log-dir> <tag>
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
from pathlib import Path

# Official normalisation constants (challenge spec text).
REF_DECODE = 0.013890
REF_PREFILL = 0.0003845
# Constants the harness itself reports as the official-runner baselines, and the
# ones recovered by regressing published officialScore on published raw legs.
HARNESS_DECODE = 0.01385621216015625
HARNESS_PREFILL = 0.00036751938916015626


def official_ns(decode: float, prefill: float) -> float:
    return (REF_DECODE / decode) ** 0.75 * (REF_PREFILL / prefill) ** 0.25


def harness_ns(decode: float, prefill: float) -> float:
    return (HARNESS_DECODE / decode) ** 0.75 * (HARNESS_PREFILL / prefill) ** 0.25


def extract_json_blocks(text: str) -> list[dict]:
    """Find every top-level {...} block that parses as JSON with a 'score' key."""
    blocks: list[dict] = []
    starts = [m.start() for m in re.finditer(r"^\s*\{\s*$", text, re.MULTILINE)]
    for s in starts:
        depth = 0
        for i in range(s, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    frag = text[s : i + 1]
                    try:
                        obj = json.loads(frag)
                    except Exception:
                        pass
                    else:
                        if isinstance(obj, dict):
                            blocks.append(obj)
                    break
    return blocks


def pick_score_block(blocks: list[dict]) -> dict | None:
    for obj in blocks:
        if "score" in obj and "decode_s_per_tok" in json.dumps(obj):
            return obj
    for obj in blocks:
        if "score" in obj:
            return obj
    return None


def deep_get(obj, key):
    """Find first occurrence of key anywhere in a nested dict/list."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = deep_get(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = deep_get(v, key)
            if r is not None:
                return r
    return None


def cv(vals: list[float]) -> float:
    if len(vals) < 2:
        return float("nan")
    return statistics.stdev(vals) / statistics.fmean(vals) * 100.0


def main() -> int:
    log_dir = Path(sys.argv[1])
    tag = sys.argv[2]
    logs = sorted(log_dir.glob(f"{tag}-*.log"), key=lambda p: p.name)
    if not logs:
        print(f"no logs matching {tag}-*.log in {log_dir}")
        return 1

    rows = []
    for p in logs:
        text = p.read_text(errors="replace")
        blocks = extract_json_blocks(text)
        sb = pick_score_block(blocks)
        if sb is None:
            print(f"{p.name}: NO SCORE JSON FOUND ({len(blocks)} json blocks)")
            continue
        dec = deep_get(sb, "decode_seconds_per_token")
        pre = deep_get(sb, "prefill_seconds_per_token")
        rows.append(
            {
                "log": p.name,
                "score": deep_get(sb, "score"),
                "passed": deep_get(sb, "passed"),
                "decode": dec,
                "prefill": pre,
                "ns": official_ns(dec, pre) if dec and pre else None,
                "ns_harness": harness_ns(dec, pre) if dec and pre else None,
                "max_abs_diff": deep_get(sb, "max_abs_diff"),
                "golden_hash": deep_get(sb, "golden_hash"),
                "harness_hash": deep_get(sb, "harness_hash"),
                "pc": deep_get(sb, "passed_correctness"),
                "pdf": deep_get(sb, "passed_decode_speedup_floor"),
                "ppf": deep_get(sb, "passed_prefill_speedup_floor"),
                "dsp": deep_get(sb, "decode_speedup"),
                "psp": deep_get(sb, "prefill_speedup"),
                "peak_ram_gb": deep_get(sb, "peak_ram_gb"),
                "timestamp": deep_get(sb, "timestamp"),
            }
        )

    print(f"=== {tag}: {len(rows)} decoded draws ===")
    hdr = f"{'draw':<24} {'score':>12} {'ns_official':>12} {'decode_s/tok':>14} {'prefill_s/tok':>15} {'pass':>5} {'ppf':>5}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['log']:<24} {r['score']:>12.6f} {r['ns']:>12.6f} "
            f"{r['decode']:>14.9f} {r['prefill']:>15.11f} "
            f"{str(r['passed']):>5} {str(r['ppf']):>5}"
        )

    for field, label in (
        ("score", "harness score"),
        ("ns", "ns (spec consts)"),
        ("ns_harness", "ns (harness consts)"),
        ("decode", "decode s/tok"),
        ("prefill", "prefill s/tok"),
    ):
        vals = [r[field] for r in rows if r[field] is not None]
        if len(vals) < 2:
            continue
        m = statistics.fmean(vals)
        sd = statistics.stdev(vals)
        sem = sd / math.sqrt(len(vals))
        print(
            f"\n{label:<22} n={len(vals)} mean={m:.9f} sd={sd:.9f} "
            f"cv={sd/m*100:.4f}% sem={sem:.9f} "
            f"95%CI=[{m-1.96*sem:.9f},{m+1.96*sem:.9f}] "
            f"min={min(vals):.9f} max={max(vals):.9f}"
        )

    print("\n--- invariants across draws ---")
    for field in ("max_abs_diff", "golden_hash", "harness_hash", "pc", "pdf", "ppf", "peak_ram_gb"):
        uniq = sorted({json.dumps(r[field]) for r in rows})
        flag = "OK  " if len(uniq) == 1 else "VARY"
        print(f"{flag} {field:<20} {uniq if len(uniq) > 1 else uniq[0]}")

    out = log_dir / f"{tag}-parsed.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
