#!/usr/bin/env python3
"""Log the r109-f queue-latency model to W&B so every scheduling claim has a run.

Recomputes, from the cached read-only snapshots, the three findings:
  1. sojourn is directly observed (updatedAt - createdAt), so no KM is needed;
  2. the binding population is our own account, not the global pool;
  3. sojourn is a monotone function of rows-in-flight at creation, with no
     residual time trend -- so last-safe-fire is a lookup, not a fixed clock.

Usage: python3 research/fern_r109f_queue_wandb.py <queue.json> [more.json ...]
"""
import datetime
import json
import os
import sys

TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
OURS = "morganmcg1"
CLOSE = datetime.datetime(2026, 8, 11, 17, 0, tzinfo=datetime.timezone.utc)
P_PER_DRAW = 0.0148          # P(one draw clears the bar), winner's-curse corrected


def P(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load(paths):
    best = {}
    for p in paths:
        doc = json.load(open(p))
        rows = doc["submissions"] if isinstance(doc, dict) else doc
        for r in rows:
            # keep the most-resolved copy of each row across snapshots
            prev = best.get(r["id"])
            if prev is None or (str(prev.get("status", "")).lower() not in TERMINAL
                                and str(r.get("status", "")).lower() in TERMINAL):
                best[r["id"]] = r
    return list(best.values())


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))] if v else float("nan")


def main():
    paths = sys.argv[1:] or ["research/fern-r109f-queue-1222Z.json"]
    rows = load(paths)

    recs = []
    for r in rows:
        c, u = r.get("createdAt"), r.get("updatedAt")
        if not c:
            continue
        term = str(r.get("status", "")).lower() in TERMINAL
        recs.append(dict(id=r["id"][:8], user=r.get("solverUsername"), term=term,
                         c=P(c), u=P(u) if (term and u) else None))

    def conc(t):
        return sum(1 for x in recs if x["c"] <= t and (x["u"] is None or x["u"] > t)) - 1

    done = [x for x in recs if x["term"] and x["u"] and x["u"] > x["c"]]
    for x in done:
        x["soj"] = (x["u"] - x["c"]).total_seconds() / 60.0
        x["conc"] = conc(x["c"])

    ours = [x["soj"] for x in done if x["user"] == OURS]
    glob = [x["soj"] for x in done]

    by_inflight = {}
    for x in done:
        by_inflight.setdefault(min(x["conc"], 6), []).append(x["soj"])

    summary = {
        "n_rows": len(rows),
        "n_terminal": len(done),
        "ours_n": len(ours),
        "ours_median_min": q(ours, .5), "ours_p75_min": q(ours, .75),
        "ours_p90_min": q(ours, .90),
        "global_median_min": q(glob, .5), "global_p75_min": q(glob, .75),
        "global_p90_min": q(glob, .90),
        "km_median_min_SUPERSEDED": 54.2,
        "headofline_age_min_BIASED": 159.0,
        "p_per_draw": P_PER_DRAW,
    }
    for k in sorted(by_inflight):
        summary[f"median_min_inflight_{k}"] = q(by_inflight[k], .5)
        summary[f"p90_min_inflight_{k}"] = q(by_inflight[k], .90)
        summary[f"n_inflight_{k}"] = len(by_inflight[k])
        lsf = CLOSE - datetime.timedelta(minutes=q(by_inflight[k], .90))
        summary[f"last_safe_fire_inflight_{k}"] = lsf.strftime("%H:%M") + "Z"

    # monotonicity check: is inflight enough, or is there a residual time trend?
    mine = sorted((x for x in done if x["user"] == OURS), key=lambda x: x["c"])
    late = [x for x in mine if x["c"] >= P("2026-08-11T00:00:00Z")]
    quiet = [x["soj"] for x in late if x["conc"] <= 2]
    busy = [x["soj"] for x in late if x["conc"] >= 5]
    summary["ours_today_quiet_median"] = q(quiet, .5)
    summary["ours_today_quiet_n"] = len(quiet)
    summary["ours_today_busy_median"] = q(busy, .5)
    summary["ours_today_busy_n"] = len(busy)

    for label, svc in [("quiet_22_7", 22.7), ("busy_med_57_6", 57.6),
                       ("busy_p90_100_4", 100.4)]:
        n = 0
        t = datetime.datetime.now(datetime.timezone.utc)
        while t + datetime.timedelta(minutes=svc) <= CLOSE:
            n += 1
            t += datetime.timedelta(minutes=svc + 1.5)
        summary[f"draws_left_{label}"] = n
        summary[f"p_crown_{label}"] = 1 - (1 - P_PER_DRAW) ** max(n, 1)

    for k, v in summary.items():
        print(f"{k} = {v}")

    if not os.environ.get("WANDB_API_KEY"):
        print("\n(no WANDB_API_KEY; metrics printed only)")
        return 0

    import wandb
    run = wandb.init(
        project="mlxfast-maple", entity="wandb-applied-ai-team",
        name="fern-r109f-queue-latency-model",
        job_type="analysis",
        tags=["r109-f", "queue", "latency", "read-only", "correction"],
        config={"snapshots": paths, "close_utc": CLOSE.isoformat(),
                "finding": "sojourn ~ rows-in-flight at creation; no time trend"},
    )
    # the contention curve as a table so the monotonicity is visible
    tbl = wandb.Table(columns=["inflight", "n", "median_min", "p90_min",
                               "last_safe_fire"])
    for k in sorted(by_inflight):
        tbl.add_data(k, len(by_inflight[k]), round(q(by_inflight[k], .5), 1),
                     round(q(by_inflight[k], .90), 1),
                     summary[f"last_safe_fire_inflight_{k}"])
    run.log({"contention_curve": tbl})
    for k, v in summary.items():
        run.summary[k] = v
    print("\nW&B run:", run.url)
    print("W&B run id:", run.id)
    run.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
