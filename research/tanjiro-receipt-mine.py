#!/usr/bin/env python3
"""Mine the public mlxfast submission API for official M5 receipts.

Every submission whose workflow reached the timed step publishes its complete
`officialMetrics`, including `prefill_seconds_per_token`,
`decode_seconds_per_token`, and the same-session pinned-baseline values -- for
`rejected` submissions as well as accepted ones. That makes the ranked host's
timing observables readable without spending a submission.

Fetch:
    curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
      "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
      -o /tmp/subs.json
"""

import json
import statistics as st
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs.json"


def obs(prefill_spt, decode_spt):
    s = 512_000.0 * prefill_spt
    return s, 1000.0 * decode_spt - s / 128.0


def main():
    subs = json.load(open(PATH))["submissions"]
    timed = [s for s in subs
             if (s.get("officialMetrics") or {}).get("decode_seconds_per_token")]
    print(f"submissions: {len(subs)}   with published timing: {len(timed)}")

    best = max(s["officialScore"] for s in timed if s["officialScore"])
    print(f"best published score: {best:.6f}\n")

    print("--- slowest published receipts: how far below the frontier a receipt "
          "can be and still publish ---")
    hdr = ("sub", "status", "score", "/best", "d_sp", "p_sp", "wall_s", "ttft")
    print("%-9s %-9s %8s %7s %8s %8s %7s %6s" % hdr)
    for s in sorted(timed, key=lambda x: x["officialScore"] or 9e9)[:6]:
        m = s["officialMetrics"]
        print("%-9s %-9s %8.4f %7.3f %8.4f %8.4f %7d %6.2f" % (
            s["id"][:8], s["status"], s["officialScore"],
            s["officialScore"] / best, m["decode_speedup"],
            m["prefill_speedup"], m.get("benchmark_wall_seconds") or 0,
            m.get("gpqa_ttft_seconds") or 0.0))

    ds = sorted(m["decode_speedup"] for m in
                (s["officialMetrics"] for s in timed))
    ps = sorted(m["prefill_speedup"] for m in
                (s["officialMetrics"] for s in timed))
    print(f"\ndecode_speedup  min {ds[0]:.4f}  median {ds[len(ds)//2]:.4f}  "
          f"max {ds[-1]:.4f}   (hard floor 0.95)")
    print(f"prefill_speedup min {ps[0]:.4f}  median {ps[len(ps)//2]:.4f}  "
          f"max {ps[-1]:.4f}   (hard floor 0.95)")

    wall = [m["benchmark_wall_seconds"] for m in
            (s["officialMetrics"] for s in timed)
            if m.get("benchmark_wall_seconds")]
    ttft = [m["gpqa_ttft_seconds"] for m in
            (s["officialMetrics"] for s in timed)
            if m.get("gpqa_ttft_seconds")]
    print(f"benchmark_wall_seconds min {min(wall)} median "
          f"{st.median(wall):.0f} max {max(wall)}")
    print(f"gpqa_ttft_seconds      min {min(ttft):.2f} median "
          f"{st.median(ttft):.2f} max {max(ttft):.2f}   (gate 2.5)")

    print("\n--- ranked-host session noise, from the pinned baseline measured "
          "beside every candidate ---")
    sb, tb = [], []
    for s in timed:
        m = s["officialMetrics"]
        a, b = obs(m["baseline_prefill_seconds_per_token"],
                   m["baseline_decode_seconds_per_token"])
        sb.append(a)
        tb.append(b)
    for name, xs in (("baseline S (ms)", sb), ("baseline T (ms)", tb)):
        print(f"{name:16s} n={len(xs):4d} mean={st.mean(xs):9.4f} "
              f"sd={st.stdev(xs):7.4f} ({100*st.stdev(xs)/st.mean(xs):.3f}%) "
              f"range={min(xs):.4f}..{max(xs):.4f}")

    print("\n--- the ranked frontier's own observables ---")
    top = sorted(timed, key=lambda x: -(x["officialScore"] or 0))[:5]
    print("%-9s %-16s %8s %10s %9s" % ("sub", "solver", "score", "S (ms)",
                                       "T (ms)"))
    for s in top:
        m = s["officialMetrics"]
        a, b = obs(m["prefill_seconds_per_token"],
                   m["decode_seconds_per_token"])
        print("%-9s %-16s %8.4f %10.3f %9.4f" % (
            s["id"][:8], s["solverUsername"][:16], s["officialScore"], a, b))


if __name__ == "__main__":
    main()
