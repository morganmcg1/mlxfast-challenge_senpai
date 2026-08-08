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

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.paths = []

    def get(self, path):
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
        output = io.StringIO()

        with redirect_stdout(output):
            watcher.wait_for_submission(
                client,
                self.scope,
                "abc",
                interval=15,
                deadline=60,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["event"], "submission_terminal")
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["promotion_status"], "promoted")
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

        with redirect_stdout(io.StringIO()):
            watcher.wait_for_submission(
                client,
                self.scope,
                "abc",
                interval=15,
                deadline=60,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

        self.assertEqual(clock.now, 20)

        with self.assertRaises(watcher.ApiError):
            watcher.wait_for_submission(
                FakeClient([watcher.ApiError(403, "forbidden")]),
                self.scope,
                "abc",
                interval=15,
                deadline=60,
                monotonic=Clock().monotonic,
                sleep=lambda _seconds: None,
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
            )
        self.assertEqual(clock.now, 20)

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
