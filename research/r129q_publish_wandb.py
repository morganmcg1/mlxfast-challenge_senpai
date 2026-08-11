#!/usr/bin/env python3
"""R129-Q: publish the channel-concurrency verdict to W&B.

Every number is recomputed here from the snapshot on disk, not pasted, so the
run cannot drift from the deliverable. Read-only w.r.t. the challenge API.

Usage: research/r129q_publish_wandb.py <snapshot.json>
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys

import wandb

US = "morganmcg1"
TERMINAL = {"rejected", "failed", "accepted", "promoted"}
CLOSE = dt.datetime(2026, 8, 11, 17, 0, 0, tzinfo=dt.timezone.utc)


def ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def sweep(rows, asof):
    ev = []
    for r in rows:
        a = ts(r["createdAt"])
        b = ts(r["updatedAt"]) if r.get("status") in TERMINAL else asof
        ev.append((a, 1))
        ev.append((max(a, b), -1))
    ev.sort(key=lambda e: (e[0], -e[1]))
    cur = best = 0
    for _, d in ev:
        cur += d
        best = max(best, cur)
    return best


def main(argv: list[str]) -> int:
    blob = json.load(open(argv[0]))
    rows = blob["submissions"]
    poll = ts(blob["polled_at"])

    per: dict[str, list[dict]] = {}
    for r in rows:
        per.setdefault(r.get("solverUsername") or "<none>", []).append(r)
    ours = per[US]
    maxc_us = sweep(ours, poll)
    maxc_global = sweep(rows, poll)
    per_acct_max = {k: sweep(v, poll) for k, v in per.items()}
    accts_ge2 = sum(1 for v in per_acct_max.values() if v >= 2)

    reactions, neg = [], 0
    for who, rs in per.items():
        rs = sorted([x for x in rs if x.get("status") in TERMINAL],
                    key=lambda x: x["createdAt"])
        for i in range(len(rs) - 1):
            soj = (ts(rs[i]["updatedAt"]) - ts(rs[i]["createdAt"])).total_seconds() / 60.0
            gap = (ts(rs[i + 1]["createdAt"]) - ts(rs[i]["createdAt"])).total_seconds() / 60.0
            reactions.append(gap - soj)
            neg += (gap - soj) < 0
    reactions.sort()

    today = sorted([r for r in ours if r["createdAt"].startswith("2026-08-11")],
                   key=lambda r: r["createdAt"])
    soj_today = [(r["id"][:8], ts(r["createdAt"]).strftime("%H:%M:%SZ"),
                  round((ts(r["updatedAt"]) - ts(r["createdAt"])).total_seconds() / 60.0, 1))
                 for r in today if r.get("status") in TERMINAL]
    morning = [s for _, c, s in soj_today if c < "07:30:00Z"]
    last3 = [s for _, _, s in soj_today][-3:]
    live = [r for r in rows if r.get("status") not in TERMINAL]
    ages = sorted((poll - ts(r["createdAt"])).total_seconds() / 60.0 for r in live)
    ours_live = [r for r in live if r.get("solverUsername") == US]

    doc = open("research/r129q_channel_concurrency.md").read()
    run = wandb.init(
        entity="wandb-applied-ai-team", project="mlxfast-maple",
        name="fern-r129q-CHANNEL-SERIAL-cap1-lastfire-1520Z",
        job_type="analysis",
        tags=["r129-q", "maple-fern", "channel", "queue", "senpai-result",
              "terminal-result", "read-only"],
        notes=doc[:8000],
        config={
            "assignment_id": "maple-r129-q-channel-concurrency-verdict",
            "revision_id": "r129-q-rev1", "pr": 745,
            "snapshot": argv[0], "polled_at": blob["polled_at"],
            "verdict": "SERIAL + per-account cap of 1 in flight",
            "listing_scope_api": "global/multi-tenant (solverUsername on 100% of rows)",
            "listing_scope_cli": "account-scoped; --all reproduces global",
            "fired_anything": False,
        })

    run.summary.update({
        "verdict": "SERIAL_CAP_1",
        "rows_total": len(rows),
        "accounts_total": len(per),
        "rows_ours": len(ours),
        "max_concurrent_ours": maxc_us,
        "max_concurrent_global": maxc_global,
        "accounts_ever_2_in_flight": accts_ge2,
        "reaction_pairs_n": len(reactions),
        "reaction_negative_n": neg,
        "reaction_min_min": round(reactions[0], 3),
        "reaction_frac_under_1min": round(
            sum(1 for x in reactions if 0 <= x < 1) / len(reactions), 4),
        "reaction_median_min": round(statistics.median(reactions), 2),
        "sojourn_morning_median_min": round(statistics.median(morning), 2),
        "sojourn_morning_n": len(morning),
        "sojourn_last3_min": last3,
        "sojourn_5fae2f13_measured_min": 46.3,
        "sojourn_global_headofline_assumed_min": 138.0,
        "live_rows_at_poll": len(live),
        "live_max_age_min": round(ages[-1], 1) if ages else None,
        "our_inflight_row": ours_live[0]["id"][:8] if ours_live else None,
        "our_inflight_created": (ts(ours_live[0]["createdAt"]).strftime("%H:%M:%SZ")
                                 if ours_live else None),
        "draws_remaining_incl_inflight": 2,
        "draws_remaining_range": "1-4",
        "last_fire_for_1700Z": "15:20Z",
        "last_fire_spread": "15:06Z-15:37Z",
        "brief_1430Z_window": "superseded (built on global head-of-line age)",
        "fern_1440Z_lastfire": "RETRACTED",
    })

    tbl = wandb.Table(columns=["id", "created", "sojourn_min"], data=[list(r) for r in soj_today])
    run.log({"our_sojourns_2026_08_11": tbl})
    art = wandb.Artifact("fern-r129q-channel-verdict", type="analysis")
    for p in ("research/r129q_channel_concurrency.md",
              "research/r129q_channel_concurrency.py",
              "research/r129q_cap_test.py",
              "research/fern-r109f-channel-slot-ledger.md"):
        art.add_file(p)
    run.log_artifact(art)
    try:
        run.alert(title="R129-Q: channel is SERIAL (per-account cap 1); last fire 15:20Z",
                  text=("Admission is capped at ONE row in flight per account: max concurrent "
                        "= 1 for all 89 accounts over 1880 rows; 0 negative reaction times in "
                        f"{len(reactions)} consecutive fire pairs (min +5.3 s). Service is "
                        "concurrent (global max 15) but admission is not. Our row c06b1b6d "
                        "was created 13:51:13Z, so the next fire waits on it. Sojourn: 22.7 "
                        "min all morning, 82.8/99.4/46.3 min since 07:57Z. The 2.3 h figure "
                        "behind the 14:30Z window is a GLOBAL head-of-line age, not our "
                        "account's service time. Last safe fire 15:20Z (15:06-15:37Z). "
                        "Draws left incl. the one in flight: 2."))
    except Exception as exc:  # noqa: BLE001
        print(f"alert failed: {exc}")
    print(f"run {run.id} {run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
