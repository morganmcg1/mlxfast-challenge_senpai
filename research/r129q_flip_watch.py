#!/usr/bin/env python3
"""fern R129-Q: read-only watch for the moment our in-flight row goes terminal.

Why this exists.  R129-Q's verdict is a hard per-account cap of ONE submission
in flight, so the campaign's next draw cannot be admitted until the row that is
currently resident on the shared account flips.  The operational rule that
follows is "fire the instant it flips" (waiting has no upside: the draw is
i.i.d., and in-flight depth is growing ~0.12 rows/min, so every extra minute of
delay makes the next sojourn longer).  That rule needs one input that no
document can supply in advance: the flip time itself.

So this job polls the GLOBAL listing (the only endpoint that reports every
account, hence also global depth) every `--interval` seconds and exits the
moment the tracked row leaves `validating`, printing the terminal status, the
official score if there is one, and the measured sojourn.  A supervised job
that exits on the event wakes the conversation immediately, which is the whole
point -- a poll that is merely logged is worth nothing if nobody reads it for
twenty minutes.

It also watches for the one observation that would REFUTE the SERIAL verdict:
two of our own rows non-terminal at the same time.  If that appears it is
reported as REFUTATION with both ids, because being wrong here is worth more to
the campaign than being confirmed (it would double the remaining draws).

Read-only: a single HTTP GET per poll.  No submit, no probe fire, ever.

usage: r129q_flip_watch.py --track c06b1b6d [--interval 150] [--until 16:20]
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
TOKEN = os.environ.get("MLXFAST_API_TOKEN", "")
BID = os.environ.get("MLXFAST_BENCHMARK_ID", "1854efdf-feba-4773-bae9-b80520881a74")
US = "morganmcg1"
TERMINAL = {"rejected", "failed", "accepted", "promoted"}
CLOSE = "17:00Z"


def now():
    return dt.datetime.now(dt.timezone.utc)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def emit(**kw):
    kw.setdefault("at", now().isoformat())
    print(json.dumps(kw), flush=True)


def get_rows():
    req = urllib.request.Request(
        API.rstrip("/") + f"/api/benchmarks/{BID}/submissions",
        headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))["submissions"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True,
                    help="id prefix of the row to watch")
    ap.add_argument("--interval", type=float, default=150.0)
    ap.add_argument("--until", default="16:20", help="HH:MM UTC hard stop")
    a = ap.parse_args()

    hh, mm = (int(x) for x in a.until.split(":"))
    stop = now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    emit(event="watch_start", track=a.track, interval=a.interval,
         until=stop.isoformat(), close=CLOSE)

    while True:
        t = now()
        if t >= stop:
            emit(event="watch_deadline", note="hard stop reached, still resident")
            return 2
        try:
            rows = get_rows()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            emit(event="poll_error", error=repr(e)[:200])
            time.sleep(a.interval)
            continue

        live = [r for r in rows if r.get("status") not in TERMINAL]
        ours_live = [r for r in live if r.get("solverUsername") == US]
        tracked = next((r for r in rows
                        if str(r.get("id", "")).startswith(a.track)), None)

        if len(ours_live) >= 2:
            emit(event="REFUTATION_SERIAL_CAP",
                 note="two own rows non-terminal at once: the per-account cap "
                      "of 1 is WRONG and the campaign has more draws",
                 ids=[r.get("id") for r in ours_live],
                 created=[r.get("createdAt") for r in ours_live])

        if tracked is None:
            emit(event="tracked_absent", global_inflight=len(live))
            time.sleep(a.interval)
            return 3

        status = tracked.get("status")
        created = ts(tracked["createdAt"])
        age = (t - created).total_seconds() / 60.0
        if status in TERMINAL:
            updated = ts(tracked["updatedAt"])
            emit(event="FLIP",
                 id=tracked.get("id"), status=status,
                 created=tracked["createdAt"], updated=tracked["updatedAt"],
                 sojourn_min=round((updated - created).total_seconds() / 60, 2),
                 official_score=tracked.get("officialScore"),
                 improved=tracked.get("improved"),
                 global_inflight_after=len(live),
                 ours_live_after=[r.get("id") for r in ours_live],
                 note="ACCOUNT SLOT IS FREE -- fire now if a candidate is ready; "
                      f"minutes left to {CLOSE}: "
                      f"{round((stop.replace(hour=17, minute=0) - t).total_seconds()/60, 1)}")
            return 0

        emit(event="poll", id=tracked.get("id"), status=status,
             age_min=round(age, 2), global_inflight=len(live),
             ours_live=[r.get("id") for r in ours_live],
             rows=len(rows))
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
