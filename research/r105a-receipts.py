#!/usr/bin/env python3
"""Collect the r105-A ranked-ladder receipts and derive the per-arm prefill cost.

Reads the arm manifest (``research/r105a-receipts.json``), fetches each
submission's official metrics, derives the prefill/decode decomposition used by
the round-105-A design bar, and prints a Markdown table. With ``--wandb`` the
same series is logged as one W&B run so the receipt sequence is durable.

The manifest is the only hand-maintained state: a list of
``{"arm", "submission_id", "commit", "queued_at"}`` objects in ladder order.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "research" / "r105a-receipts.json"
BENCHMARK = "eigenlabs/mlxfast-challenge"

# Pinned calibration baselines used by the ranked wrapper's health check, taken
# from the r105-A assignment. They normalise receipts whose same-session paired
# baseline drifted, so arms measured in different sessions stay comparable.
CAL_DEC = 0.013890
CAL_PRE = 0.0003845


def api(path: str) -> dict:
    cfg = json.loads((pathlib.Path.home() / ".config" / "mlxfast" / "config.json").read_text())
    key = cfg.get("apiKey") or cfg.get("api_key")
    base = cfg.get("apiUrl") or "https://api.mlx.fast"
    request = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {key}"})
    return json.load(urllib.request.urlopen(request, timeout=120))


def fetch_rows(ids: list[str]) -> dict[str, dict]:
    # Per-id reads cost ~14 KB each against ~17 MB for the whole benchmark feed,
    # and the feed is also not guaranteed to still carry an older submission.
    rows = {}
    for sid in ids:
        rows[sid] = api(f"/api/submissions/{urllib.parse.quote(sid, safe='')}")["submission"]
    return rows


def derive(metrics: dict) -> dict:
    dec = metrics["decode_seconds_per_token"]
    pre = metrics["prefill_seconds_per_token"]
    prefill_ms = 512_000.0 * pre
    step_ms = 1000.0 * dec - prefill_ms / 128.0
    nd = CAL_DEC / dec
    npf = CAL_PRE / pre
    # Score sensitivity to one millisecond of prefill wall. The prefill wall is
    # charged twice: once through the prefill axis and once through the decode
    # axis, where the 512-token seed is amortised over the 128 timed steps.
    price = 100.0 * (0.75 / (128_000.0 * dec) + 0.25 / (512_000.0 * pre))
    return {
        "cand_dec": dec,
        "cand_pre": pre,
        "prefill_ms": prefill_ms,
        "step_ms": step_ms,
        "norm_decode_su": nd,
        "norm_prefill_su": npf,
        "norm_score": nd**0.75 * npf**0.25,
        "prefill_price_pct_per_ms": price,
        "baseline_dec": metrics["baseline_decode_seconds_per_token"],
        "baseline_pre": metrics["baseline_prefill_seconds_per_token"],
        "decode_speedup": metrics["decode_speedup"],
        "prefill_speedup": metrics["prefill_speedup"],
        "max_abs_diff": metrics["max_abs_diff"],
        "passed_correctness": metrics["passed_correctness"],
        "passed_decode_floor": metrics["passed_decode_speedup_floor"],
        "passed_prefill_floor": metrics["passed_prefill_speedup_floor"],
        "checked_steps": metrics["checked_steps"],
        "semantic_gpqa": f"{metrics['semantic_gpqa_pass_count']}/{metrics['semantic_gpqa_case_count']}",
        "gpqa_ttft_passed": metrics["gpqa_ttft_passed"],
        "gpqa_ttft_p50_seconds": metrics["gpqa_ttft_p50_seconds"],
        "measured_at": metrics["timestamp"],
        "service_commit": metrics["commit"],
        "error": metrics["error"],
        "partial_result": metrics["partial_result"],
    }


BAR_MS = 1.35
# One-sided 95 % Student-t, indexed by degrees of freedom.
T95 = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860}


def _sd(xs: list[float]) -> float:
    mean = sum(xs) / len(xs)
    return (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def analyse(records: list[dict]) -> dict:
    """Contrast each treatment arm against the A0 control mean (§4.3, §4.4.2).

    The per-receipt sigma is measured from the A0 replicates rather than assumed
    from the public cross-submission spread, which §4.4.1 shows overstates it by
    ~10x. Delta is measured on the candidate-prefill channel, so its SE must come
    from that same channel: the decode channel is a correlated re-measurement of
    the same seed prefill, so pooling it would understate the SE and taking
    whichever channel happens to be tighter would let the false-positive rate
    float with the noise draw.
    """
    arms: dict[str, list[dict]] = {}
    for r in records:
        if "prefill_ms" in r:
            arms.setdefault(r["arm"].split("-")[0], []).append(r)
    out: dict = {"arm_receipt_counts": {k: len(v) for k, v in sorted(arms.items())}}

    control = arms.get("A0", [])
    if len(control) < 2:
        out["status"] = "needs >=2 A0 receipts to measure sigma"
        return out

    prefill = [r["prefill_ms"] for r in control]
    decode = [128_000.0 * r["cand_dec"] for r in control]
    n0 = len(control)
    sigma_p, sigma_q = _sd(prefill), _sd(decode)
    sigma = sigma_p
    out.update(
        control_n=n0,
        control_dof=n0 - 1,
        control_mean_prefill_ms=sum(prefill) / n0,
        control_mean_decode_ms=sum(decode) / n0,
        control_mean_step_ms=sum(r["step_ms"] for r in control) / n0,
        sigma_prefill_channel_ms=sigma_p,
        sigma_decode_channel_ms=sigma_q,
        sigma_ms=sigma,
        sigma_pct=100.0 * sigma / (sum(prefill) / n0),
    )

    for name, rs in sorted(arms.items()):
        if name == "A0":
            continue
        n = len(rs)
        nu = (n0 - 1) + (n - 1)
        t = T95[min(nu, max(T95))]
        se = sigma * (1.0 / n + 1.0 / n0) ** 0.5
        delta = out["control_mean_prefill_ms"] - sum(r["prefill_ms"] for r in rs) / n
        echo = out["control_mean_decode_ms"] - sum(128_000.0 * r["cand_dec"] for r in rs) / n
        step = out["control_mean_step_ms"] - sum(r["step_ms"] for r in rs) / n
        lo, hi = delta - t * se, delta + t * se
        if lo > BAR_MS:
            verdict = "WIN" if n >= 2 else "WIN-pending-replicate"
        elif hi < 0.0:
            verdict = "REGRESSION"
        elif hi < BAR_MS:
            verdict = "NULL-bar-excluded"
        elif delta > 2.0 * se:
            verdict = "PROMISING-needs-replicate"
        else:
            verdict = "NULL-underpowered"
        out[name] = {
            "n": n,
            "dof": nu,
            "t95": t,
            "se_ms": se,
            "delta_prefill_ms": delta,
            "delta_decode_echo_ms": echo,
            "delta_step_ms": step,
            "ci90_ms": [lo, hi],
            "z_vs_zero": delta / se,
            "verdict": verdict,
            "verdict_is_shippable": verdict == "WIN",
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wandb", action="store_true", help="log the series to W&B")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    rows = fetch_rows([entry["submission_id"] for entry in manifest])
    records = []
    for entry in manifest:
        row = rows.get(entry["submission_id"])
        record = {
            "arm": entry["arm"],
            "submission_id": entry["submission_id"],
            "commit": entry["commit"],
            "queued_at": entry["queued_at"],
            "status": (row or {}).get("status", "missing"),
            "official_score": (row or {}).get("officialScore"),
            "rejection_reason": (row or {}).get("rejectionReason"),
        }
        metrics = (row or {}).get("officialMetrics")
        if metrics:
            record.update(derive(metrics))
            record["commit_reported"] = metrics.get("commit")
        records.append(record)

    header = (
        "| arm | commit | status | score | prefill ms | step ms | nd | np | ns | %/ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    )
    print("\n".join(header))
    for r in records:
        if "prefill_ms" in r:
            print(
                f"| {r['arm']} | `{r['commit'][:8]}` | {r['status']} | "
                f"{r['official_score']:.5f} | {r['prefill_ms']:.3f} | {r['step_ms']:.4f} | "
                f"{r['norm_decode_su']:.5f} | {r['norm_prefill_su']:.5f} | "
                f"{r['norm_score']:.5f} | {r['prefill_price_pct_per_ms']:.4f} |"
            )
        else:
            print(f"| {r['arm']} | `{r['commit'][:8]}` | {r['status']} | - | - | - | - | - | - | - |")

    contrast = analyse(records)
    print("\n### contrast against the A0 control (§4.4.2)")
    print(json.dumps(contrast, indent=1))

    out = ROOT / "research" / "r105a-receipts-resolved.json"
    out.write_text(json.dumps({"receipts": records, "contrast": contrast}, indent=1) + "\n")
    print(f"\nwrote {out.relative_to(ROOT)}")

    if args.wandb:
        import wandb

        run = wandb.init(
            entity="wandb-applied-ai-team",
            project="mlxfast-maple",
            name="r105-a-ranked-ladder",
            job_type="ranked-receipt-ladder",
            config={
                "assignment_id": "maple-r105-a-afrag-ntile-reuse",
                "revision_id": "r105-a-rev2",
                "pr": 592,
                "branch": "maple-tanjiro/r105-afrag-ntile-reuse",
                "base_sha": "5f7861c0981278929c3ef43d54a6d5bca10a8659",
                "origin_main_sha": "1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7",
                "design_bar_prefill_ms": BAR_MS,
                "assumed_sigma_pct_of_score_prereg": 0.1588,
                "calibration_decode_seconds_per_token": CAL_DEC,
                "calibration_prefill_seconds_per_token": CAL_PRE,
                "ladder_order": "A0-1,A0-2,A2-1,A0-3,A1-1,replicate-leader,replicate-other,combined-or-third",
            },
        )
        table = wandb.Table(columns=sorted({k for r in records for k in r}))
        for step, r in enumerate(records):
            row = [r.get(c) for c in table.columns]
            table.add_data(*row)
            scalars = {f"receipt/{k}": v for k, v in r.items() if isinstance(v, (int, float))}
            if scalars:
                run.log({**scalars, "receipt/index": step, "arm": r["arm"]}, step=step)
        run.log({"receipts": table})
        run.summary["receipt_count"] = len(records)
        accepted = [r for r in records if r.get("official_score")]
        if accepted:
            run.summary["best_official_score"] = max(r["official_score"] for r in accepted)
        for key, value in contrast.items():
            if isinstance(value, dict):
                for sub, subvalue in value.items():
                    run.summary[f"contrast/{key}/{sub}"] = subvalue
            else:
                run.summary[f"contrast/{key}"] = value
        print(f"wandb run: {run.url}")
        run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
