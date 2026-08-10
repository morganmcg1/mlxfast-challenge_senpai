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


def fetch_rows() -> dict[str, dict]:
    bench = api(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")
    bid = bench.get("benchmark", bench)["id"]
    rows = api(f"/api/benchmarks/{bid}/submissions")["submissions"]
    return {row["id"]: row for row in rows}


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
        "decode_speedup": metrics["decode_speedup"],
        "prefill_speedup": metrics["prefill_speedup"],
        "max_abs_diff": metrics["max_abs_diff"],
        "passed_correctness": metrics["passed_correctness"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wandb", action="store_true", help="log the series to W&B")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    rows = fetch_rows()
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

    out = ROOT / "research" / "r105a-receipts-resolved.json"
    out.write_text(json.dumps(records, indent=1) + "\n")
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
                "design_bar_prefill_ms": 1.35,
                "receipt_sigma_pct_of_score": 0.1588,
                "calibration_decode_seconds_per_token": CAL_DEC,
                "calibration_prefill_seconds_per_token": CAL_PRE,
                "ladder_order": "A0-1,A0-2,A2-1,A1-1,A0-3,A1-2,A2-2,spare",
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
        print(f"wandb run: {run.url}")
        run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
