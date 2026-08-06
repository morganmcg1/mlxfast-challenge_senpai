"""Read one official receipt out of the submissions feed and score it against
the PR #35 r5-B pre-registration.

Analysis-only helper (not part of the challenge runtime).
Usage: python3 research/frieren_pr35_receipt_read.py <feed.json> <short_id>
"""

import json
import sys

NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845

# Paired baseline receipt 0c21dc18, re-verified against the live feed.
BASE_NS = 2.529734001523645
BASE_S_MS = 98.029375
BASE_T_MS = 4.3181484375

MDE_PCT = 0.278
PRICE_LO_PCT = 0.58

SCALARS = [
    "decode_seconds_per_token",
    "prefill_seconds_per_token",
    "baseline_decode_seconds_per_token",
    "baseline_prefill_seconds_per_token",
    "checked_tokens",
    "decode_steps",
    "repeats",
    "peak_ram_gb",
]
FLAGS = [
    "passed",
    "passed_correctness",
    "passed_prefill_speedup_floor",
    "passed_decode_speedup_floor",
]
STRINGS = [
    "error",
    "commit",
    "golden_hash",
    "harness_hash",
    "weights_hash",
    "first_failing_case",
    "first_failing_layer",
    "first_failing_step",
]


def coerce(value):
    """officialMetrics arrives as a JSON-encoded string in the public feed."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def find(obj, key):
    obj = coerce(obj)
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for sub in obj.values():
            got = find(sub, key)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for sub in obj:
            got = find(sub, key)
            if got is not None:
                return got
    return None


def planes(decode_spt, prefill_spt):
    ns = (NORM_DECODE / decode_spt) ** 0.75 * (NORM_PREFILL / prefill_spt) ** 0.25
    s_ms = 512000.0 * prefill_spt
    t_ms = 1000.0 * decode_spt - s_ms / 128.0
    return ns, s_ms, t_ms


def reading(delta_ns_pct):
    if delta_ns_pct >= PRICE_LO_PCT:
        return "STRONG CONFIRMATION (>= +0.60%/+0.58% priced band)"
    if delta_ns_pct >= 0.15:
        return "REPORT ONLY, do not resubmit (+0.15%..+0.60%)"
    if delta_ns_pct >= -MDE_PCT:
        return "INSIDE SINGLE-RECEIPT NOISE (-0.28%..+0.15%)"
    return "REGRESSION, report immediately (< -0.28%)"


def main():
    feed_path, short = sys.argv[1], sys.argv[2]
    feed = json.load(open(feed_path))
    if isinstance(feed, dict):
        for key in ("submissions", "items", "data", "results"):
            if isinstance(feed.get(key), list):
                feed = feed[key]
                break
    hits = [s for s in feed if str(s.get("id", "")).startswith(short)]
    if not hits:
        sys.exit(f"no submission in {feed_path} with id prefix {short}")
    sub = max(hits, key=lambda s: str(s.get("updatedAt", "")))

    print(f"== submission {sub.get('id')} ==")
    for key in (
        "status",
        "officialScore",
        "claimedScore",
        "promotionStatus",
        "improved",
        "rejectionReason",
        "submissionCommitSha",
        "solverUsername",
        "createdAt",
        "updatedAt",
    ):
        print(f"{key:22s}: {sub.get(key)!r}")

    metrics = coerce(sub.get("officialMetrics"))
    if not isinstance(metrics, (dict, list)):
        print("\nno structured officialMetrics yet (submission not terminal)")
        return

    print("\n-- gate flags --")
    for key in FLAGS:
        print(f"{key:32s}: {find(metrics, key)!r}")
    print("\n-- strings --")
    for key in STRINGS:
        print(f"{key:32s}: {find(metrics, key)!r}")
    print("\n-- scalars --")
    for key in SCALARS:
        print(f"{key:34s}: {find(metrics, key)!r}")

    d = find(metrics, "decode_seconds_per_token")
    p = find(metrics, "prefill_seconds_per_token")
    if not isinstance(d, (int, float)) or not isinstance(p, (int, float)):
        print("\nno paired timing in receipt")
        return

    ns, s_ms, t_ms = planes(d, p)
    print("\n-- derived planes (candidate) --")
    print(f"ns                : {ns:.9f}")
    print(f"S (prefill, ms)   : {s_ms:.6f}")
    print(f"T (steady, ms)    : {t_ms:.7f}")
    print("\n-- versus paired baseline 0c21dc18 --")
    for name, cand, base, better_low in (
        ("ns", ns, BASE_NS, False),
        ("S_ms", s_ms, BASE_S_MS, True),
        ("T_ms", t_ms, BASE_T_MS, True),
    ):
        pct = 100.0 * (cand - base) / base
        sign = "faster" if (pct < 0) == better_low else "slower"
        print(f"{name:6s} base={base:.9f} cand={cand:.9f} delta={pct:+.4f}% ({sign})")

    delta_ns = 100.0 * (ns - BASE_NS) / BASE_NS
    print(f"\nPREREG READING: {reading(delta_ns)}")
    print(f"delta ns = {delta_ns:+.4f}%  (MDE +/-{MDE_PCT}%, priced +{PRICE_LO_PCT}%..+0.67%)")


if __name__ == "__main__":
    main()
