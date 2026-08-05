#!/usr/bin/env python3
"""Read the PR #48 ranked receipt and apply the §9.1 pre-registered verdict.

The `mlxfast submissions` CLI truncates `details` and has no `--json`, so the
full metric set has to come from the submissions endpoint:

    curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
      "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
      -o /tmp/subs.json

Ranking is on the renormalised `ns`, never on `officialScore`: 86.5-86.9% of
officialScore's variance is the same-session baseline-prefill draw, which is a
property of the draw rather than of the candidate's content.

Usage: maple-fern-pr48-receipt.py [subs.json] [submission-id-prefix]
"""

import json
import sys

# §9.1 renormalisation constants and the fixed control.
ND_NUM = 0.013890      # decode s/tok that renormalises to nd = 1
NPF_NUM = 0.0003845    # prefill s/tok that renormalises to npf = 1
CONTROL_NS = 2.544360  # c3ce66ec, the frozen-frontier control
TICKET = "285f79fa-089f-4184-b1ec-0647cb51e61b"

# Legacy acceptance band. Removed from the local notice but still enforced by
# `tolerances`, `Score.swift`, and four test files.
BAND = {"decode": (0.980, 1.053), "prefill": (0.952, 1.053)}

# §9.1 pre-registered verdict table, keyed on the ns delta vs CONTROL_NS.
BANDS = [
    (2.02, None, "READING A -- clears the P=95% promotion bar; merge and open "
                 "the dispatch-count axis programme-wide"),
    (1.50, 2.02, "A-LEANING -- merge (beats the current best); axis stays open"),
    (0.90, 1.50, "AMBIGUOUS -- no mechanism claim; hand to tanjiro's "
                 "DARKBLOOM_INJECT_SWEEP_PASSES discriminator"),
    (0.00, 0.90, "READING B -- dispatch-count axis closes; merge only if it "
                 "beats control; no mechanism claim"),
    (None, 0.00, "NEGATIVE -- report immediately, do not resubmit"),
]


def ns_of(decode_spt, prefill_spt):
    """Renormalised content score: ns = nd^0.75 * npf^0.25."""
    nd = ND_NUM / decode_spt
    npf = NPF_NUM / prefill_spt
    return nd ** 0.75 * npf ** 0.25, nd, npf


def st_of(decode_spt, prefill_spt):
    """Prefill wall S (ms) and prefill-netted decode T (ms), tanjiro's convention."""
    s = 512_000.0 * prefill_spt
    return s, 1000.0 * decode_spt - s / 128.0


def verdict(delta_pct):
    for lo, hi, text in BANDS:
        if (lo is None or delta_pct >= lo) and (hi is None or delta_pct < hi):
            return text
    return "UNCLASSIFIED"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs.json"
    want = sys.argv[2] if len(sys.argv) > 2 else TICKET

    subs = json.load(open(path))["submissions"]
    mine = [s for s in subs if s["id"].startswith(want[:8])]
    if not mine:
        print(f"ticket {want[:8]} not in feed ({len(subs)} submissions)")
        return 1

    sub = mine[0]
    print(f"submission {sub['id']}")
    print(f"status     {sub['status']}")
    print(f"created    {sub.get('createdAt')}")
    print(f"score      {sub.get('officialScore')}   (officialScore -- NOT ranked on)")

    m = sub.get("officialMetrics") or {}
    if not m.get("decode_seconds_per_token"):
        print("\nno published timing yet -- the run has not reached the timed step")
        return 0

    print("\n--- correctness gates ---")
    for k in ("passed_correctness", "max_abs_diff", "checked_steps", "case_count",
              "num_layers", "first_failing_case", "first_failing_layer",
              "first_failing_step", "error"):
        print(f"  {k:34s} {m.get(k)!r}")

    print("\n--- hidden gates ---")
    for k in ("gpqa_ttft_passed", "gpqa_ttft_case_count", "gpqa_ttft_pass_count",
              "gpqa_ttft_p50_seconds", "gpqa_ttft_max_seconds",
              "semantic_gpqa_passed", "semantic_gpqa_case_count",
              "semantic_gpqa_pass_count"):
        print(f"  {k:34s} {m.get(k)!r}")

    print("\n--- floors (the two that decide rankability) ---")
    for k in ("decode_speedup", "passed_decode_speedup_floor", "decode_speedup_floor",
              "prefill_speedup", "passed_prefill_speedup_floor", "prefill_speedup_floor"):
        print(f"  {k:34s} {m.get(k)!r}")

    print("\n--- provenance ---")
    for k in ("commit", "golden_hash", "harness_hash", "weights_hash",
              "peak_ram_gb", "process_resident_memory_gb", "runtime", "timestamp"):
        print(f"  {k:34s} {m.get(k)!r}")

    d = m["decode_seconds_per_token"]
    p = m["prefill_seconds_per_token"]
    bd = m.get("baseline_decode_seconds_per_token")
    bp = m.get("baseline_prefill_seconds_per_token")

    print("\n--- timing observables ---")
    print(f"  decode_seconds_per_token           {d!r}")
    print(f"  prefill_seconds_per_token          {p!r}")
    print(f"  baseline_decode_seconds_per_token  {bd!r}")
    print(f"  baseline_prefill_seconds_per_token {bp!r}")

    s_ms, t_ms = st_of(d, p)
    print(f"  S (prefill wall, ms)               {s_ms:.4f}")
    print(f"  T (prefill-netted decode, ms)      {t_ms:.5f}")

    ns, nd, npf = ns_of(d, p)
    delta = (ns / CONTROL_NS - 1.0) * 100.0
    print("\n--- §9.1 renormalised ranking ---")
    print(f"  nd = {ND_NUM}/{d} = {nd:.6f}")
    print(f"  npf = {NPF_NUM}/{p} = {npf:.6f}")
    print(f"  ns = nd^0.75 * npf^0.25 = {ns:.6f}")
    print(f"  control c3ce66ec ns     = {CONTROL_NS:.6f}")
    print(f"  delta vs control        = {delta:+.4f}%")
    print(f"\n  PRE-REGISTERED VERDICT: {verdict(delta)}")

    band_report(m, subs)
    return 0


def band_place(ratio, lo, hi):
    if lo <= ratio <= hi:
        return "IN BAND", 0.0
    if ratio < lo:
        return "BELOW lo", (ratio - lo) / lo * 100.0
    return "ABOVE hi", (ratio - hi) / hi * 100.0


def band_report(m, subs):
    """Hand-compute the legacy band under BOTH circulating conventions.

    The advisor flagged that two students use incompatible definitions. They
    are reciprocals: `speedup` = baseline/candidate (higher is better), and
    `time-ratio` = candidate/baseline (lower is better). The band ceiling of
    1.053 reads naturally as a +5.3% *gain* cap, i.e. as a speedup band. Both
    are printed here, alongside the unchanged control, so the comparison is
    settled by arithmetic rather than by convention.
    """
    control = next((s for s in subs if s["id"].startswith("c3ce66e")), None)
    cm = (control or {}).get("officialMetrics") or {}

    print("\n--- legacy acceptance band, hand-computed, BOTH conventions ---")
    print("  Removed from the local notice; still enforced by `tolerances`,")
    print("  `Score.swift` and four test files. AGENTS.md states the deployed")
    print("  wrapper does not cap candidate gains at 1.053 and treats those")
    print("  inner invocations as timing probes.")
    print(f"  {'axis':8s} {'conv':10s} {'candidate':>10s} {'control':>10s}  band            verdict")
    for axis in ("decode", "prefill"):
        lo, hi = BAND[axis]
        cand = m.get(f"{axis}_speedup")
        ctrl = cm.get(f"{axis}_speedup")
        if cand is None:
            continue
        for conv, f in (("speedup", lambda r: r), ("time-ratio", lambda r: 1.0 / r)):
            cv = f(cand)
            where, margin = band_place(cv, lo, hi)
            ctrl_s = f"{f(ctrl):10.6f}" if ctrl else f"{'n/a':>10s}"
            print(f"  {axis:8s} {conv:10s} {cv:10.6f} {ctrl_s}  [{lo}, {hi}]  "
                  f"{where} ({margin:+.2f}%)")
    print("  If the control fails a cell as badly as the candidate does, that")
    print("  cell is not a live gate -- it is a convention artefact.")


if __name__ == "__main__":
    sys.exit(main())
