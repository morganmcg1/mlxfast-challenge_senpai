#!/usr/bin/env python3
"""Wait for an MLXFast submission receipt without busy-polling."""

from __future__ import annotations

import argparse
import email.utils
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar


DEFAULT_API_URL = "https://api.mlx.fast"
DEFAULT_BENCHMARK = "eigenlabs/mlxfast-challenge"
DEFAULT_POLL_INTERVAL_SECONDS = 180
POLL_JITTER_SECONDS = 20
MIN_POLL_INTERVAL_SECONDS = 60
ACTIVE_SUBMISSION_STATUSES = frozenset({"queued", "validating"})
ACTIVE_PROMOTION_STATUSES = frozenset({"queued", "promoting"})
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504, 529})
T = TypeVar("T")


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    token: str


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str, retry_after: Optional[float] = None):
        super().__init__(f"MLXFast API returned HTTP {status}: {message}")
        self.status = status
        self.retry_after = retry_after


class ApiClient:
    def __init__(self, config: ApiConfig):
        self.config = config

    def get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {self.config.token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")[:500]
            body = body.replace(self.config.token, "<redacted>")
            retry_after = error.headers.get("Retry-After") if error.headers else None
            raise ApiError(
                error.code,
                body,
                parse_retry_after(retry_after),
            ) from error


def load_api_config() -> ApiConfig:
    config_path = Path.home() / ".config" / "mlxfast" / "config.json"
    stored: dict[str, Any] = {}
    if config_path.exists():
        stored = json.loads(config_path.read_text(encoding="utf-8"))
    base_url = (
        os.environ.get("MLXFAST_API_URL")
        or os.environ.get("YUKON_API_URL")
        or stored.get("apiBaseUrl")
        or DEFAULT_API_URL
    )
    token = (
        os.environ.get("MLXFAST_API_TOKEN")
        or os.environ.get("YUKON_API_TOKEN")
        or os.environ.get("SUPABASE_ACCESS_TOKEN")
        or stored.get("token")
    )
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("mlxfast login or MLXFAST_API_TOKEN is required")
    return ApiConfig(base_url=str(base_url), token=token)


def resolve_scope(
    client: ApiClient,
    benchmark_ref: str,
) -> tuple[str, str]:
    account_id = client.get("/api/me")["account"]["id"]
    encoded_ref = urllib.parse.quote(benchmark_ref, safe="")
    benchmark = client.get(f"/api/benchmarks/{encoded_ref}")["benchmark"]
    return account_id, benchmark["id"]


def account_submissions(
    client: ApiClient,
    scope: tuple[str, str],
) -> list[dict[str, Any]]:
    account_id, benchmark_id = scope
    submissions = client.get(f"/api/benchmarks/{benchmark_id}/submissions")[
        "submissions"
    ]
    return [row for row in submissions if row.get("solverAccountId") == account_id]


def resolve_submission(
    submissions: list[dict[str, Any]],
    reference: str,
) -> dict[str, Any]:
    reference = reference.strip()
    if not reference:
        raise RuntimeError("submission ID or prefix is required")
    matches = [row for row in submissions if str(row.get("id", "")).startswith(reference)]
    if not matches:
        raise RuntimeError(f"submission {reference!r} was not found for this account")
    if len(matches) > 1:
        raise RuntimeError(f"submission prefix {reference!r} is ambiguous")
    return matches[0]


def emit(event: str, **fields: Any) -> None:
    print(
        json.dumps(
            {
                "event": event,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                **fields,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = email.utils.parsedate_to_datetime(value).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None
        return max(0, math.ceil(retry_at - (time.time() if now is None else now)))
    return math.ceil(seconds) if math.isfinite(seconds) and seconds >= 0 else None


def retry_delay(interval: float, error: Exception) -> float:
    if isinstance(error, ApiError) and error.retry_after is not None:
        return max(interval, error.retry_after)
    return interval


def retryable(error: Exception) -> bool:
    return not isinstance(error, ApiError) or error.status in RETRYABLE_HTTP_STATUSES


def read_with_retry(
    read: Callable[[], T],
    interval: float,
    deadline: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    while monotonic() < deadline:
        try:
            return read()
        except (ApiError, OSError) as error:
            if not retryable(error):
                raise
            sleep(min(retry_delay(interval, error), max(0, deadline - monotonic())))
    raise TimeoutError("MLXFast API remained unavailable before timeout")


def submission_is_active(row: dict[str, Any]) -> bool:
    status = str(row.get("status", "unknown")).lower()
    promotion = str(row.get("promotionStatus", "")).lower()
    return status in ACTIVE_SUBMISSION_STATUSES or (
        status == "accepted" and promotion in ACTIVE_PROMOTION_STATUSES
    )


def exact_submission(
    client: ApiClient,
    submission_id: str,
    scope: tuple[str, str],
) -> dict[str, Any]:
    account_id, benchmark_id = scope
    encoded_id = urllib.parse.quote(submission_id, safe="")
    row = client.get(f"/api/submissions/{encoded_id}")["submission"]
    if row.get("solverAccountId") != account_id:
        raise RuntimeError(f"submission {submission_id!r} does not belong to this account")
    if row.get("benchmarkId") != benchmark_id:
        raise RuntimeError(f"submission {submission_id!r} belongs to another benchmark")
    return row


def wait_for_submission(
    client: ApiClient,
    scope: tuple[str, str],
    reference: str,
    interval: float,
    deadline: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    uniform: Callable[[float, float], float] = random.uniform,
) -> None:
    submission_id: Optional[str] = None
    while monotonic() < deadline:
        row = read_with_retry(
            lambda: (
                resolve_submission(account_submissions(client, scope), reference)
                if submission_id is None
                else exact_submission(client, submission_id, scope)
            ),
            interval,
            deadline,
            monotonic=monotonic,
            sleep=sleep,
        )
        submission_id = str(row["id"])
        if not submission_is_active(row):
            emit(
                "submission_terminal",
                submission_id=submission_id,
                status=row.get("status", "unknown"),
                promotion_status=row.get("promotionStatus"),
                promotion_reason=row.get("promotionReason"),
                official_score=row.get("officialScore"),
                commit=row.get("submissionCommitSha"),
            )
            return
        poll_delay = interval + uniform(0, POLL_JITTER_SECONDS)
        sleep(min(poll_delay, max(0, deadline - monotonic())))
    raise TimeoutError("submission remained active before timeout")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Wait without busy-polling for one of this account's submissions to "
            "reach a terminal state."
        )
    )
    parser.add_argument("--submission", required=True, help="ID or unique prefix")
    parser.add_argument(
        "--benchmark",
        default=os.environ.get("MLXFAST_BENCHMARK_REF", DEFAULT_BENCHMARK),
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=(
            "base polling interval before an independent 0-20 second jitter "
            f"(default: {DEFAULT_POLL_INTERVAL_SECONDS})"
        ),
    )
    parser.add_argument("--timeout-seconds", type=float, default=21_600)
    args = parser.parse_args()
    if (
        not math.isfinite(args.interval_seconds)
        or args.interval_seconds < MIN_POLL_INTERVAL_SECONDS
    ):
        parser.error(
            f"--interval-seconds must be at least {MIN_POLL_INTERVAL_SECONDS}"
        )
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    args.submission = args.submission.strip()
    if not args.submission:
        parser.error("--submission must not be empty")
    return args


def main() -> int:
    args = parse_args()
    emit("watching_submission", submission_id=args.submission)
    client = ApiClient(load_api_config())
    deadline = time.monotonic() + args.timeout_seconds
    scope = read_with_retry(
        lambda: resolve_scope(client, args.benchmark),
        args.interval_seconds,
        deadline,
    )
    wait_for_submission(
        client,
        scope,
        args.submission,
        args.interval_seconds,
        deadline,
    )
    return 0


def cli() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("submission watcher interrupted", file=sys.stderr)
        return 130
    except (ApiError, RuntimeError, TimeoutError, OSError, KeyError, ValueError) as error:
        print(f"submission watcher failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
