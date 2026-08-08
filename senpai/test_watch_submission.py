import importlib.util
import io
import json
import sys
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("watch-submission.py")
SPEC = importlib.util.spec_from_file_location("watch_submission", SCRIPT)
assert SPEC and SPEC.loader
watcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watcher
SPEC.loader.exec_module(watcher)


def submission(
    submission_id="abc123",
    *,
    status="validating",
    promotion_status=None,
):
    return {
        "id": submission_id,
        "benchmarkId": "benchmark-id",
        "solverAccountId": "account-id",
        "status": status,
        "promotionStatus": promotion_status,
        "officialScore": 2.5 if status == "accepted" else None,
        "submissionCommitSha": "deadbeef",
    }


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.paths = []

    def get(self, path, **_request):
        self.paths.append(path)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class SubmissionWatcherTests(unittest.TestCase):
    scope = ("account-id", "benchmark-id")

    def test_resolves_only_an_unambiguous_account_submission_prefix(self):
        rows = [submission("abc123"), submission("def456")]

        self.assertEqual(watcher.resolve_submission(rows, "abc"), rows[0])
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            watcher.resolve_submission([*rows, submission("abc456")], "abc")
        with self.assertRaisesRegex(RuntimeError, "not found"):
            watcher.resolve_submission(rows, "missing")

    def test_waits_through_validation_and_promotion_then_emits_one_receipt(self):
        client = FakeClient(
            [
                {"submissions": [submission()]},
                {"submission": submission(status="accepted", promotion_status="queued")},
                {"submission": submission(status="accepted", promotion_status="promoted")},
            ]
        )
        clock = Clock()
        uniform = mock.Mock(side_effect=[3, 17])
        output = io.StringIO()

        with redirect_stdout(output):
            watcher.wait_for_submission(
                client,
                self.scope,
                "abc",
                interval=180,
                deadline=500,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
                uniform=uniform,
            )

        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["event"], "submission_terminal")
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["promotion_status"], "promoted")
        self.assertEqual(clock.sleeps, [183, 197])
        self.assertEqual(
            uniform.call_args_list,
            [mock.call(0, watcher.POLL_JITTER_SECONDS)] * 2,
        )
        self.assertEqual(
            client.paths,
            [
                "/api/benchmarks/benchmark-id/submissions",
                "/api/submissions/abc123",
                "/api/submissions/abc123",
            ],
        )

    def test_retries_only_transient_reads_and_honors_retry_after(self):
        transient = watcher.ApiError(429, "busy", retry_after=20)
        client = FakeClient(
            [transient, {"submissions": [submission(status="rejected")]}]
        )
        clock = Clock()
        uniform = mock.Mock(return_value=7)

        with redirect_stdout(io.StringIO()):
            watcher.wait_for_submission(
                client,
                self.scope,
                "abc",
                interval=15,
                deadline=60,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
                uniform=uniform,
            )

        self.assertEqual(clock.now, 27)
        uniform.assert_called_once_with(0, watcher.POLL_JITTER_SECONDS)

        with self.assertRaises(watcher.ApiError):
            watcher.wait_for_submission(
                FakeClient([watcher.ApiError(403, "forbidden")]),
                self.scope,
                "abc",
                interval=15,
                deadline=60,
                monotonic=Clock().monotonic,
                sleep=lambda _seconds: None,
                uniform=lambda _low, _high: 0,
            )

    def test_timeout_does_not_sleep_past_its_deadline(self):
        clock = Clock()
        with self.assertRaisesRegex(TimeoutError, "remained active"):
            watcher.wait_for_submission(
                FakeClient([{"submissions": [submission()]}]),
                self.scope,
                "abc",
                interval=60,
                deadline=20,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
                uniform=lambda _low, _high: watcher.POLL_JITTER_SECONDS,
            )
        self.assertEqual(clock.now, 20)

    def test_cli_defaults_to_three_minute_polling_and_rejects_tight_loops(self):
        with mock.patch.object(
            sys,
            "argv",
            ["watch-submission.py", "--submission", "abc"],
        ):
            args = watcher.parse_args()

        self.assertEqual(args.interval_seconds, 180)
        self.assertEqual(watcher.MIN_POLL_INTERVAL_SECONDS, 180)
        self.assertEqual(watcher.POLL_JITTER_SECONDS, 20)

        with mock.patch.object(
            sys,
            "argv",
            [
                "watch-submission.py",
                "--submission",
                "abc",
                "--interval-seconds",
                "179",
            ],
        ):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                watcher.parse_args()

    def test_status_and_promotion_states_fail_closed_when_unknown(self):
        active = [
            submission(status="queued"),
            submission(status="validating"),
            submission(status="accepted", promotion_status="queued"),
            submission(status="accepted", promotion_status="promoting"),
        ]
        terminal = [
            submission(status="failed"),
            submission(status="rejected"),
            submission(status="accepted", promotion_status="failed"),
            submission(status="accepted", promotion_status="promoted"),
            submission(status="accepted", promotion_status="rejected"),
        ]

        self.assertTrue(all(watcher.submission_is_active(row) for row in active))
        self.assertTrue(
            all(not watcher.submission_is_active(row) for row in terminal)
        )
        with self.assertRaisesRegex(RuntimeError, "unknown submission status"):
            watcher.submission_is_active(submission(status="processing"))
        with self.assertRaisesRegex(RuntimeError, "unknown promotion status"):
            watcher.submission_is_active(submission(status="accepted"))

    def test_exact_receipt_must_match_account_and_benchmark_scope(self):
        with self.assertRaisesRegex(RuntimeError, "does not belong to this account"):
            watcher.exact_submission(
                FakeClient(
                    [
                        {
                            "submission": {
                                **submission(),
                                "solverAccountId": "other-account",
                            }
                        }
                    ]
                ),
                "abc123",
                self.scope,
            )
        with self.assertRaisesRegex(RuntimeError, "another benchmark"):
            watcher.exact_submission(
                FakeClient(
                    [
                        {
                            "submission": {
                                **submission(),
                                "benchmarkId": "other-benchmark",
                            }
                        }
                    ]
                ),
                "abc123",
                self.scope,
            )

    def test_retry_after_accepts_seconds_and_http_dates(self):
        self.assertEqual(watcher.parse_retry_after("1.2"), 2)
        self.assertEqual(
            watcher.parse_retry_after("Thu, 01 Jan 1970 00:02:00 GMT", now=60),
            60,
        )
        self.assertIsNone(watcher.parse_retry_after("not-a-date"))

    def test_api_client_uses_get_and_does_not_put_the_token_in_the_url(self):
        response = FakeResponse(b'{"ok":true}')
        client = watcher.ApiClient(watcher.ApiConfig("https://example.test", "secret"))

        with mock.patch.object(urllib.request, "urlopen", return_value=response) as call:
            self.assertEqual(client.get("/api/me"), {"ok": True})

        request = call.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://example.test/api/me")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertNotIn("secret", request.full_url)
        self.assertEqual(
            call.call_args.kwargs["timeout"], watcher.REQUEST_TIMEOUT_SECONDS
        )

    def test_api_request_timeout_is_bounded_by_remaining_deadline(self):
        response = FakeResponse(b'{"ok":true}')
        client = watcher.ApiClient(watcher.ApiConfig("https://example.test", "secret"))
        clock = Clock()
        clock.now = 97

        with mock.patch.object(urllib.request, "urlopen", return_value=response) as call:
            self.assertEqual(
                client.get("/api/me", deadline=100, monotonic=clock.monotonic),
                {"ok": True},
            )

        self.assertEqual(call.call_args.kwargs["timeout"], 3)
        clock.now = 100
        with mock.patch.object(urllib.request, "urlopen") as expired:
            with self.assertRaisesRegex(TimeoutError, "deadline expired"):
                client.get("/api/me", deadline=100, monotonic=clock.monotonic)
        expired.assert_not_called()

    def test_api_errors_redact_an_echoed_token(self):
        headers = Message()
        headers["Retry-After"] = "30"
        error = urllib.error.HTTPError(
            "https://example.test/api/me",
            429,
            "busy",
            headers,
            io.BytesIO(b'bad credential "secret"'),
        )
        client = watcher.ApiClient(watcher.ApiConfig("https://example.test", "secret"))

        with mock.patch.object(urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(watcher.ApiError) as raised:
                client.get("/api/me")

        self.assertNotIn("secret", str(raised.exception))
        self.assertIn("<redacted>", str(raised.exception))
        self.assertEqual(raised.exception.retry_after, 30)

    def test_interrupt_exits_cleanly_without_a_traceback(self):
        stderr = io.StringIO()
        with mock.patch.object(watcher, "main", side_effect=KeyboardInterrupt):
            with redirect_stderr(stderr):
                self.assertEqual(watcher.cli(), 130)
        self.assertEqual(stderr.getvalue(), "submission watcher interrupted\n")


if __name__ == "__main__":
    unittest.main()
