#!/usr/bin/env python3
"""Calibrate the ranked-receipt noise level per measurement channel.

The r105-A ladder can afford at most eight ranked receipts, so the per-arm
sample size is too small to estimate its own variance usefully. This script
instead calibrates the instrument offline from the public benchmark history:
whenever the same candidate commit was measured more than once, those receipts
are same-code replicates, and their spread is the paired-measurement noise.

Channels compared (all as natural logs, so a value is a relative SD):

* ``cand_pre`` / ``cand_dec``  unpaired candidate seconds-per-token
* ``base_pre`` / ``base_dec``  the same-session paired baseline
* ``ps`` / ``ds``             the published paired speedups
* ``score``                   ``0.75*ln ds + 0.25*ln ps``

Pairing is worth using only if the speedup channel is quieter than the
candidate-only channel, i.e. if session common mode dominates.

Usage: research/r105a-calibrate.py [--days N] [--json OUT]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("receipts", ROOT / "research" / "r105a-receipts.py")
_receipts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_receipts)

CHANNELS = ("cand_pre", "cand_dec", "base_pre", "base_dec", "ps", "ds", "score")


def channels(metrics: dict) -> dict[str, float] | None:
    try:
        pre = float(metrics["prefill_seconds_per_token"])
        dec = float(metrics["decode_seconds_per_token"])
        bpre = float(metrics["baseline_prefill_seconds_per_token"])
        bdec = float(metrics["baseline_decode_seconds_per_token"])
    except (TypeError, ValueError, KeyError):
        return None
    if min(pre, dec, bpre, bdec) <= 0:
        return None
    ps, ds = bpre / pre, bdec / dec
    return {
        "cand_pre": math.log(pre),
        "cand_dec": math.log(dec),
        "base_pre": math.log(bpre),
        "base_dec": math.log(bdec),
        "ps": math.log(ps),
        "ds": math.log(ds),
        "score": 0.75 * math.log(ds) + 0.25 * math.log(ps),
        "_pre": pre,
        "_dec": dec,
    }


def pooled(groups: list[list[float]]) -> tuple[float, int]:
    ss = 0.0
    dof = 0
    for values in groups:
        if len(values) < 2:
            continue
        mean = sum(values) / len(values)
        ss += sum((v - mean) ** 2 for v in values)
        dof += len(values) - 1
    return (math.sqrt(ss / dof) if dof else float("nan")), dof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=float, default=None, help="restrict to recent receipts")
    parser.add_argument("--json", type=pathlib.Path, default=None)
    parser.add_argument("--reference-harness", action="store_true", help="keep only the most common harness")
    args = parser.parse_args()

    rows = _receipts.fetch_rows()
    reference = None
    receipts = []
    now = dt.datetime.now(dt.timezone.utc)
    for row in rows.values():
        metrics = row.get("officialMetrics")
        if not isinstance(metrics, dict) or not metrics.get("passed_correctness"):
            continue
        values = channels(metrics)
        if values is None:
            continue
        created = dt.datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00"))
        if args.days is not None and (now - created).total_seconds() > args.days * 86400:
            continue
        receipts.append(
            {
                "commit": metrics.get("commit") or row.get("submissionCommitSha"),
                "harness": metrics.get("harness_hash"),
                "weights": metrics.get("weights_hash"),
                "created": created,
                "values": values,
            }
        )
    if not receipts:
        raise SystemExit("no receipts matched the filter")

    harnesses = collections.Counter(r["harness"] for r in receipts)
    reference = harnesses.most_common(1)[0][0]
    if args.reference_harness:
        receipts = [r for r in receipts if r["harness"] == reference]

    # A replicate group is the same candidate commit measured by the same
    # harness and weights, i.e. an exact same-code repeat of the paired
    # measurement. Its spread is the instrument noise.
    by_commit: dict[tuple, list[dict]] = collections.defaultdict(list)
    for receipt in receipts:
        by_commit[(receipt["harness"], receipt["weights"], receipt["commit"])].append(receipt)
    replicated = {k: v for k, v in by_commit.items() if len(v) >= 2}

    print(f"reference_harness={reference}  receipts={len(receipts)}  distinct_groups={len(by_commit)}")
    print(f"replicated_groups={len(replicated)}  replicate_receipts={sum(len(v) for v in replicated.values())}")
    print(f"harness_hashes={len(harnesses)}  weights_hashes={len(set(r['weights'] for r in receipts))}")

    # Median operating point, used to convert a relative SD into wall time.
    pre = sorted(r["values"]["_pre"] for r in receipts)[len(receipts) // 2]
    dec = sorted(r["values"]["_dec"] for r in receipts)[len(receipts) // 2]
    prefill_ms = 512_000.0 * pre
    step_ms = 1000.0 * dec - prefill_ms / 128.0
    price = 100.0 * (0.75 / (128_000.0 * dec) + 0.25 / (512_000.0 * pre))
    print(f"\noperating point: prefill_wall={prefill_ms:.3f} ms  pure_step={step_ms:.4f} ms  f={price:.4f} %/ms")

    print("\nper-receipt sigma (same-commit replicates, pooled):")
    print("| channel | sigma_1 (%) | dof | score-equivalent sigma_1 (%) | prefill-ms equivalent |")
    print("| --- | --- | --- | --- | --- |")
    summary = {}
    # Sensitivity of each channel to one millisecond of prefill wall.
    g_pre = 100.0 / prefill_ms
    g_dec = 100.0 / (128.0 * step_ms + prefill_ms)
    grad = {
        "cand_pre": g_pre,
        "cand_dec": g_dec,
        "base_pre": float("nan"),
        "base_dec": float("nan"),
        "ps": g_pre,
        "ds": g_dec,
        "score": price,
    }
    for channel in CHANNELS:
        sigma, dof = pooled([[r["values"][channel] for r in group] for group in replicated.values()])
        pct = 100.0 * sigma
        gradient = grad[channel]
        ms = pct / gradient if gradient == gradient and gradient > 0 else float("nan")
        score_equiv = ms * price if ms == ms else float("nan")
        summary[channel] = {"sigma_pct": pct, "dof": dof, "prefill_ms": ms, "score_pct": score_equiv}
        print(f"| {channel} | {pct:.4f} | {dof} | {score_equiv:.4f} | {ms:.4f} |")

    print("\ncross-session sigma of the same-code paired baseline (all receipts):")
    ordered = sorted(receipts, key=lambda r: r["created"])
    for channel in ("base_pre", "base_dec"):
        values = [r["values"][channel] for r in receipts]
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
        summary.setdefault("_baseline", {})[channel] = 100.0 * sd
        print(f"  {channel}: sigma_total={100 * sd:.4f} %  n={len(values)}")

    # The paired ratio cancels whatever the candidate and its baseline share.
    # A variogram over the same-code baseline series separates the fast part
    # (does not cancel) from the slow session/thermal part (does).
    print("\nbaseline variogram: sqrt(0.5*mean((x_i - x_j)^2)) by elapsed gap")
    print("| channel | gap | pairs | sigma_gap (%) | share of total |")
    print("| --- | --- | --- | --- | --- |")
    buckets = [(0, 900), (900, 3600), (3600, 6 * 3600), (6 * 3600, 24 * 3600), (24 * 3600, 30 * 86400)]
    for channel in ("base_pre", "base_dec"):
        total = summary["_baseline"][channel]
        for low, high in buckets:
            squares = []
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    gap = (right["created"] - left["created"]).total_seconds()
                    if gap >= high:
                        break
                    if gap >= low:
                        squares.append((right["values"][channel] - left["values"][channel]) ** 2)
            if not squares:
                continue
            sigma = 100.0 * math.sqrt(0.5 * sum(squares) / len(squares))
            label = f"{low / 60:.0f}-{high / 60:.0f} min"
            print(f"| {channel} | {label} | {len(squares)} | {sigma:.4f} | {sigma / total:.3f} |")
            summary.setdefault("_variogram", {}).setdefault(channel, {})[label] = sigma

    # Identify the session common mode. Candidate code effects live only in the
    # candidate channel, so any covariance between a receipt's candidate and its
    # own baseline is the shared per-session factor that the paired ratio
    # cancels. Pairing beats the candidate-only endpoint iff sigma_s > sigma_e.
    print("\ncommon-mode decomposition from within-receipt covariance:")
    print("| axis | sd_base (%) | sd_cand (%) | cov -> sigma_s (%) | sigma_e (%) | sigma(paired) (%) | sigma(cand-only) (%) | pairing |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for axis, base_key, cand_key in (("prefill", "base_pre", "cand_pre"), ("decode", "base_dec", "cand_dec")):
        base = [r["values"][base_key] for r in receipts]
        cand = [r["values"][cand_key] for r in receipts]
        n = len(base)
        mb, mc = sum(base) / n, sum(cand) / n
        vb = sum((b - mb) ** 2 for b in base) / (n - 1)
        vc = sum((c - mc) ** 2 for c in cand) / (n - 1)
        cov = sum((b - mb) * (c - mc) for b, c in zip(base, cand)) / (n - 1)
        sigma_s = math.sqrt(max(cov, 0.0))
        sigma_e = math.sqrt(max(vb - max(cov, 0.0), 0.0))
        paired = math.sqrt(2.0) * sigma_e
        cand_only = math.sqrt(vb)
        verdict = "helps" if paired < cand_only else "hurts"
        print(
            f"| {axis} | {100 * math.sqrt(vb):.4f} | {100 * math.sqrt(vc):.4f} | {100 * sigma_s:.4f} | "
            f"{100 * sigma_e:.4f} | {100 * paired:.4f} | {100 * cand_only:.4f} | {verdict} |"
        )
        summary.setdefault("_decomposition", {})[axis] = {
            "sd_base_pct": 100 * math.sqrt(vb),
            "sd_cand_pct": 100 * math.sqrt(vc),
            "sigma_session_pct": 100 * sigma_s,
            "sigma_run_pct": 100 * sigma_e,
            "sigma_paired_pct": 100 * paired,
            "sigma_cand_only_pct": 100 * cand_only,
        }

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "harness_hash": reference,
                    "receipts": len(receipts),
                    "replicated_commits": len(replicated),
                    "prefill_ms": prefill_ms,
                    "step_ms": step_ms,
                    "price_pct_per_ms": price,
                    "channels": summary,
                },
                indent=2,
            )
            + "\n"
        )
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
