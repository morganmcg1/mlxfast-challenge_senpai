#!/usr/bin/env python3
"""Watch a ranked submission's organizer-side CI run without any credential.

`senpai/watch-submission.py` needs the MLXFast API token, which only exists in
an interactive shell session. The organizer repository's Actions API answers
unauthenticated for everything except artifact *download*, so a submission can
be followed end to end from the public side instead. Step-level conclusions are
strictly more informative than the submission status string: they show exactly
which gate stopped the run and whether the timing steps were ever reached.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ORG_REPO = "Layr-Labs/mlxfast-challenge"
API = f"https://api.github.com/repos/{ORG_REPO}"


def get(path: str) -> tuple[int, object]:
    request = urllib.request.Request(
        API + path,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "senpai-research"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")[:300]
    except Exception as error:  # transient DNS/TLS/socket failures must not end the watch
        return 0, str(error)


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def find_benchmark_run(submission: str) -> dict | None:
    status, body = get(f"/actions/runs?branch=submissions/{submission}&per_page=20")
    if status != 200 or not isinstance(body, dict):
        emit("list_runs_failed", status=status, detail=body)
        return None
    for run in body.get("workflow_runs", []):
        if run.get("name") == "benchmark":
            return run
    return None


def report_steps(run_id: int) -> None:
    status, body = get(f"/actions/runs/{run_id}/jobs")
    if status != 200 or not isinstance(body, dict):
        emit("list_jobs_failed", status=status, detail=body)
        return
    for job in body.get("jobs", []):
        emit(
            "job",
            name=job.get("name"),
            status=job.get("status"),
            conclusion=job.get("conclusion"),
            runner=job.get("runner_name"),
            url=job.get("html_url"),
        )
        for step in job.get("steps", []):
            emit(
                "step",
                job=job.get("name"),
                number=step.get("number"),
                name=step.get("name"),
                conclusion=step.get("conclusion"),
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission", required=True)
    parser.add_argument("--interval-seconds", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=int, default=5100)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout_seconds
    emit("watching", submission=args.submission, repo=ORG_REPO)

    while True:
        run = find_benchmark_run(args.submission)
        if run is not None:
            emit(
                "run",
                id=run.get("id"),
                status=run.get("status"),
                conclusion=run.get("conclusion"),
                url=run.get("html_url"),
            )
            if run.get("status") == "completed":
                report_steps(int(run["id"]))
                emit("terminal", conclusion=run.get("conclusion"))
                return 0
        if time.monotonic() >= deadline:
            emit("timeout")
            return 1
        time.sleep(min(args.interval_seconds, max(1, deadline - time.monotonic())))


if __name__ == "__main__":
    sys.exit(main())
