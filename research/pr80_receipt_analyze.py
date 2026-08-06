#!/usr/bin/env python3
"""Analyse the ranked mlxfast receipt for PR #80 from the submissions API dump.

The `mlxfast` CLI truncates the `metrics` blob and has no `--json` flag, so the
full record has to come from the REST API:

    MLXFAST_API_TOKEN="${MLXFAST_API_TOKEN:-}" python3 - <<'EOF'
    import json, os, urllib.request
    req = urllib.request.Request(
        "https://api.mlx.fast/api/benchmarks/"
        "eigenlabs%2Fmlxfast-challenge/submissions",
        headers={"Authorization": "Bearer " + os.environ["MLXFAST_API_TOKEN"]})
    open("/tmp/pr80_subs.json", "wb").write(urllib.request.urlopen(req).read())
    EOF

The secret is injected only when the literal string MLXFAST_API_TOKEN appears in
the shell command text, so a bare `python3 fetch.py` receives nothing.

The dump is ~17 MB because every record carries its full submission note; this
script never prints a note.

    python3 research/pr80_receipt_analyze.py [dump.json] [receipt-id-prefix]
"""

import json
import statistics as st
import sys

# Pinned normalisation constants for the cross-session `ns` metric.
NS_DECODE = 0.013890
NS_PREFILL = 0.0003845

# Claimed byte saving of PR #80, from the escape census (arm A -> arm D).
CLAIM_BYTES = 27_698_336
M5_PEAK_BW = 651.8e9
M5_EFFECTIVE_BW = 546.2e9

ACCOUNT = "morganmcg1"


def ns_of(m):
    d = m.get("decode_seconds_per_token")
    p = m.get("prefill_seconds_per_token")
    if not d or not p:
        return None
    return (NS_DECODE / d) ** 0.75 * (NS_PREFILL / p) ** 0.25


def load(path):
    raw = json.load(open(path))
    return raw["submissions"] if isinstance(raw, dict) else raw


def rule(title):
    print(f"\n=== {title} ===")


def report_receipt(rec):
    m = rec["officialMetrics"]
    rule("receipt")
    print(f"  id                {rec['id']}")
    print(f"  status            {rec['status']}   improved={rec['improved']}"
          f"   promotionStatus={rec['promotionStatus']}")
    print(f"  rejectionReason   {rec['rejectionReason']}")
    print(f"  error             {m['error']!r}")
    print(f"  passed_correctness {m['passed_correctness']}"
          f"   cases={m['case_count']} checked_steps={m['checked_steps']}")
    print(f"  semantic_gpqa     {m['semantic_gpqa_passed']}"
          f" {m['semantic_gpqa_pass_count']}/{m['semantic_gpqa_case_count']}"
          f" judge={m['semantic_gpqa_model']}")
    print(f"  gpqa_ttft         {m['gpqa_ttft_passed']}"
          f" {m['gpqa_ttft_pass_count']}/{m['gpqa_ttft_case_count']}"
          f" {m['gpqa_ttft_seconds']}s p50={m['gpqa_ttft_p50_seconds']}s"
          f" cap={m['gpqa_ttft_max_seconds']}s")
    print(f"  decode_speedup    {m['decode_speedup']!r}"
          f"  floor={m['decode_speedup_floor']}"
          f"  passed={m['passed_decode_speedup_floor']}")
    print(f"  prefill_speedup   {m['prefill_speedup']!r}"
          f"  floor={m['prefill_speedup_floor']}"
          f"  passed={m['passed_prefill_speedup_floor']}")
    print(f"  officialScore     {rec['officialScore']!r}")
    print(f"  golden_hash       {m['golden_hash']}")
    print(f"  harness_hash      {m['harness_hash']}")

    d, p = m["decode_seconds_per_token"], m["prefill_seconds_per_token"]
    S = 512000 * p
    rule("normalised score")
    print(f"  norm_decode_su  = {NS_DECODE} / {d} = {NS_DECODE/d:.9f}")
    print(f"  norm_prefill_su = {NS_PREFILL} / {p} = {NS_PREFILL/p:.9f}")
    print(f"  ns              = {ns_of(m):.6f}")
    print(f"  S = 512000*prefill_spt        = {S:.4f} ms")
    print(f"  T = 1000*decode_spt - S/128   = {1000*d - S/128:.4f} ms")


def report_increment(prev, cur):
    """prev is the receipt for this PR's base commit; cur is base + PR."""
    pm, cm = prev["officialMetrics"], cur["officialMetrics"]
    dp, dc = pm["decode_seconds_per_token"], cm["decode_seconds_per_token"]
    pp, pc = pm["prefill_seconds_per_token"], cm["prefill_seconds_per_token"]

    rule(f"increment {str(prev['id'])[:7]} (base) -> {str(cur['id'])[:7]} (base + PR)")
    print(f"  base receipt note opens: {(prev.get('note') or '').splitlines()[2][:60]!r}")
    print(f"  golden_hash identical: {pm['golden_hash'] == cm['golden_hash']}")
    print(f"  harness_hash differs:  {pm['harness_hash'] != cm['harness_hash']}")
    print(f"  raw decode  {dp!r} -> {dc!r}   {100*(dp/dc-1):+.4f} %"
          f"  -> score {0.75*100*(dp/dc-1):+.4f} %")
    print(f"  raw prefill {pp!r} -> {pc!r}   {100*(pp/pc-1):+.4f} %")

    rd = cm["decode_speedup"] / pm["decode_speedup"]
    rp = cm["prefill_speedup"] / pm["prefill_speedup"]
    print(f"  drift-cancelled decode  {100*(rd-1):+.4f} %"
          f"  -> score {0.75*100*(rd-1):+.4f} %")
    print(f"  drift-cancelled prefill {100*(rp-1):+.4f} %"
          f"   <-- baseline artefact, see baseline stability below")

    rule("decode-channel ledger (denominator = candidate decode_spt)")
    for name, bw in (("bytes @ M5 peak 651.8 GB/s", M5_PEAK_BW),
                     ("bytes @ M5 effective 546.2 GB/s", M5_EFFECTIVE_BW)):
        us = CLAIM_BYTES / bw * 1e6
        print(f"  {name:<34} {us:6.2f} us  -> score {0.75*100*us/1e6/dc:+.4f} %")
    obs = (dp - dc) * 1e6
    print(f"  {'OBSERVED (raw)':<34} {obs:6.2f} us  -> score {0.75*100*obs/1e6/dc:+.4f} %")
    eff = CLAIM_BYTES / M5_EFFECTIVE_BW * 1e6
    print(f"  observed/peak={obs/(CLAIM_BYTES/M5_PEAK_BW*1e6):.2f}x"
          f"  observed/effective={obs/eff:.2f}x"
          f"  instruction residual={obs-eff:.2f} us"
          f" ({(obs-eff)/eff:.2f}x the byte share)")


def report_baseline_stability(subs, cur, n=40):
    have = [s for s in subs
            if (s.get("officialMetrics") or {}).get("baseline_decode_seconds_per_token")]
    have.sort(key=lambda s: s["createdAt"])
    recent = have[-n:]
    bd = [s["officialMetrics"]["baseline_decode_seconds_per_token"] for s in recent]
    bp = [s["officialMetrics"]["baseline_prefill_seconds_per_token"] for s in recent]
    rsd_d = st.stdev(bd) / st.mean(bd)
    rsd_p = st.stdev(bp) / st.mean(bp)

    rule(f"pinned-baseline stability over the last {len(recent)} scored sessions")
    print(f"  baseline_decode_spt  mean={st.mean(bd):.10f} rel_sd={100*rsd_d:.4f} %"
          f" p2p={100*(max(bd)/min(bd)-1):.3f} %")
    print(f"  baseline_prefill_spt mean={st.mean(bp):.11f} rel_sd={100*rsd_p:.4f} %"
          f" p2p={100*(max(bp)/min(bp)-1):.3f} %")
    print(f"  prefill baseline is {rsd_p/rsd_d:.1f}x noisier than the decode baseline")

    m = cur["officialMetrics"]
    z = (m["baseline_prefill_seconds_per_token"] - st.mean(bp)) / st.stdev(bp)
    print(f"  this session's baseline_prefill_spt ="
          f" {m['baseline_prefill_seconds_per_token']!r}  ({z:+.2f} sigma)")

    rule("robustness of the promotion to that baseline draw")
    d, p = m["decode_seconds_per_token"], m["prefill_seconds_per_token"]
    as_measured = ((m["baseline_decode_seconds_per_token"] / d) ** 0.75
                   * (m["baseline_prefill_seconds_per_token"] / p) ** 0.25)
    normalised = (st.mean(bd) / d) ** 0.75 * (st.mean(bp) / p) ** 0.25
    prior = [s for s in subs
             if s.get("officialScore") and s["createdAt"] < cur["createdAt"]
             and s["status"] == "accepted"]
    prev_best = max(s["officialScore"] for s in prior)
    print(f"  as measured            officialScore = {as_measured:.9f}"
          f"  (receipt {cur['officialScore']:.9f})")
    print(f"  baselines set to mean  officialScore = {normalised:.9f}")
    print(f"  previous best                        = {prev_best:.9f}")
    print(f"    margin as measured        = {as_measured-prev_best:+.6f}"
          f"  ({100*(as_measured/prev_best-1):+.3f} %)")
    print(f"    margin baseline-normalised = {normalised-prev_best:+.6f}"
          f"  ({100*(normalised/prev_best-1):+.3f} %)")


def report_ladder(subs, cur):
    rule("ns ladder")
    prior = [s for s in subs
             if s.get("officialScore") and s["createdAt"] < cur["createdAt"]
             and s["status"] == "accepted"]
    top = sorted(prior, key=lambda s: -s["officialScore"])[:3]
    rows = [(cur, "THIS")] + [(s, "") for s in top]
    for s, tag in rows:
        print(f"  ns={ns_of(s['officialMetrics']):.6f}"
              f"  officialScore={s['officialScore']:.9f}"
              f"  {str(s['id'])[:7]}  {s['solverUsername']:<14}"
              f" {s['promotionStatus']}  {s['createdAt'][:19]} {tag}")

    rule(f"last 6 {ACCOUNT} receipts")
    ours = sorted([s for s in subs
                   if s.get("solverUsername") == ACCOUNT and s.get("officialScore")],
                  key=lambda s: s["createdAt"])
    for s in ours[-6:]:
        m = s["officialMetrics"]
        print(f"  {s['createdAt'][:19]}  {str(s['id'])[:7]}"
              f"  ns={ns_of(m):.6f}  officialScore={s['officialScore']:.9f}"
              f"  {s['status']}/{s['promotionStatus']}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pr80_subs.json"
    want = sys.argv[2] if len(sys.argv) > 2 else "97a5090"
    subs = load(path)

    cur = next((s for s in subs if str(s["id"]).startswith(want)), None)
    if cur is None:
        sys.exit(f"receipt {want} not found in {path} ({len(subs)} records)")

    ours = sorted([s for s in subs
                   if s.get("solverUsername") == ACCOUNT and s.get("officialScore")],
                  key=lambda s: s["createdAt"])
    prev = ours[ours.index(cur) - 1]

    report_receipt(cur)
    report_ladder(subs, cur)
    report_increment(prev, cur)
    report_baseline_stability(subs, cur)


if __name__ == "__main__":
    main()
