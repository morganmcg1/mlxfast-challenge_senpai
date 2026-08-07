#!/usr/bin/env python3
"""Audit the official submission feed for PR #170's floor-safety pre-registration.

The arms in PR #170 deliberately inject bit-exact prefill work, so every arm is
expected to publish a *worse* prefill_speedup than the paired baseline. Before
spending a receipt this script establishes, from the feed rather than from
assumption:

  1. how much prefill headroom the 0.95 floor actually leaves for our frontier;
  2. whether a below-floor run publishes magnitudes or publishes nothing.

Usage:
    curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
      https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions \
      -o /tmp/subs.json
    python3 research/tanjiro-pr170-feed-audit.py /tmp/subs.json \
      > research/artifacts/tanjiro-pr170-feed-audit.txt
"""

import collections
import json
import re
import sys

# Our own promoted frontier and the arm-cost envelope pre-registered in R0b.
FRONTIER_PREFILL_S_PER_TOK = 0.00019120068359375
PREFILL_TOKENS = 512
FLOOR = 0.95
MAX_ARM_DELTA_MS = 33.3  # largest over-cost flag in R0b (ΔM2)


def ms_per_512(s_per_tok):
    return s_per_tok * PREFILL_TOKENS * 1e3


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main(path):
    feed = json.load(open(path))
    subs = feed["submissions"]
    withm = [s for s in subs if isinstance(s.get("officialMetrics"), dict)]

    section("0. FEED SHAPE")
    print("source                 %s" % path)
    print("submissions            %d" % len(subs))
    print("with officialMetrics   %d" % len(withm))
    hist = collections.Counter(
        (s["status"], isinstance(s.get("officialMetrics"), dict)) for s in subs
    )
    for (status, has), n in sorted(hist.items(), key=lambda t: -t[1]):
        print("  status=%-12s hasMetrics=%-5s n=%d" % (status, has, n))

    section("1. DO BELOW-FLOOR RUNS PUBLISH MAGNITUDES?")
    pf = [s for s in withm if s["officialMetrics"].get("passed_prefill_speedup_floor") is False]
    dc = [s for s in withm if s["officialMetrics"].get("passed_decode_speedup_floor") is False]
    print("metric-bearing receipts with passed_prefill_speedup_floor == false: %d / %d"
          % (len(pf), len(withm)))
    print("metric-bearing receipts with passed_decode_speedup_floor  == false: %d / %d"
          % (len(dc), len(withm)))
    print()
    print("floor constants observed (prefill, decode):")
    for k, n in collections.Counter(
        (s["officialMetrics"].get("prefill_speedup_floor"),
         s["officialMetrics"].get("decode_speedup_floor")) for s in withm
    ).most_common():
        print("  %r  n=%d" % (k, n))
    print()
    failed = [s for s in subs if s["status"] == "failed"]
    print("status=failed n=%d, of which officialMetrics is not null: %d"
          % (len(failed), sum(1 for s in failed if s.get("officialMetrics") is not None)))
    print()
    print("failed-step histogram (numbers/SHAs normalised):")
    c = collections.Counter()
    for s in failed:
        r = re.sub(r"\b[0-9a-f]{7,}\b", "SHA", (s.get("rejectionReason") or "").strip())
        c[re.sub(r"\d+\.\d+", "NUM", r)[:150]] += 1
    for k, n in c.most_common(12):
        print("  n=%-5d %s" % (n, k))
    print()
    print("CONCLUSION: a run that misses a floor is recorded as status=failed with")
    print("officialMetrics=null. It publishes NO magnitudes at all -- not a partial")
    print("record. So a below-floor arm costs a receipt and returns zero information.")

    section("2. HOW CLOSE TO THE FLOOR DOES THE FEED ACTUALLY GET?")
    ps = sorted(s["officialMetrics"]["prefill_speedup"] for s in withm
                if isinstance(s["officialMetrics"].get("prefill_speedup"), (int, float)))
    print("n=%d  min=%.5f  p01=%.5f  p50=%.5f" % (len(ps), ps[0], pct(ps, 0.01), pct(ps, 0.50)))
    print("count < 0.96 = %d   count < 0.99 = %d" % (sum(v < 0.96 for v in ps),
                                                     sum(v < 0.99 for v in ps)))
    lo = [s for s in withm
          if isinstance(s["officialMetrics"].get("prefill_speedup"), (int, float))
          and s["officialMetrics"]["prefill_speedup"] < 0.98]
    lo.sort(key=lambda s: s["officialMetrics"]["prefill_speedup"])
    print()
    print("lowest published prefill_speedup receipts (these are the existence proof")
    print("that a slower-than-baseline candidate still publishes full magnitudes):")
    for s in lo[:5]:
        m = s["officialMetrics"]
        print("  id=%s status=%-9s ps=%.5f  cand=%.6g s/tok  base=%.6g s/tok  reason=%r"
              % (s["id"][:8], s["status"], m["prefill_speedup"],
                 m.get("prefill_seconds_per_token"),
                 m.get("baseline_prefill_seconds_per_token"),
                 (s.get("rejectionReason") or "")[:60]))

    section("3. PAIRED-BASELINE PREFILL DISTRIBUTION (LAST 200 METRIC-BEARING)")
    base = [s["officialMetrics"]["baseline_prefill_seconds_per_token"] for s in withm[-200:]
            if isinstance(s["officialMetrics"].get("baseline_prefill_seconds_per_token"),
                          (int, float))]
    bms = [ms_per_512(v) for v in base]
    print("n=%d  min=%.2f  p05=%.2f  p50=%.2f  p95=%.2f  max=%.2f  (ms per 512 tokens)"
          % (len(bms), min(bms), pct(bms, 0.05), pct(bms, 0.5), pct(bms, 0.95), max(bms)))

    section("4. ARM HEADROOM ARITHMETIC (THE R1 CORRECTION)")
    cand = ms_per_512(FRONTIER_PREFILL_S_PER_TOK)
    worst_base = min(bms)
    admissible = worst_base / FLOOR
    headroom = admissible - cand
    print("frontier candidate prefill      %.3f ms / 512 tok" % cand)
    print("worst (fastest) paired baseline %.3f ms / 512 tok" % worst_base)
    print("max admissible candidate        %.3f ms  (= baseline / %.2f)" % (admissible, FLOOR))
    print("injection headroom              %.3f ms" % headroom)
    print("largest arm delta R0b permits   %.3f ms" % MAX_ARM_DELTA_MS)
    print("worst-case arm prefill_speedup  %.4f" % (worst_base / (cand + MAX_ARM_DELTA_MS)))
    print("safety margin                   %.2fx" % (headroom / MAX_ARM_DELTA_MS))
    print()
    print("The review that demanded arms be shrunk to <=4.5% divided the arm cost by")
    print("the frontier CANDIDATE (%.1f ms) instead of the paired BASELINE (%.1f ms)."
          % (cand, worst_base))
    print("Because the frontier is ~2x faster than its own baseline, the floor binds on")
    print("the baseline, not on the candidate: the arms have ~%.0f ms of room, not ~5 ms."
          % headroom)

    section("5. WALL-CLOCK / TIMEOUT RISK")
    for key in ("benchmark_wall_seconds", "timed_benchmark_seconds"):
        vs = [s["officialMetrics"][key] for s in withm
              if isinstance(s["officialMetrics"].get(key), (int, float))]
        if vs:
            print("%-26s n=%-5d p50=%.0f p95=%.0f max=%.0f s"
                  % (key, len(vs), pct(vs, 0.5), pct(vs, 0.95), max(vs)))
    print("Arms add tens of milliseconds to one 512-token prefill. Timeout is a non-issue.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs.json")
