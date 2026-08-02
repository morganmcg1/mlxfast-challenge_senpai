from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent))

from laguna_quality.public_probe import (  # noqa: E402
    PUBLIC_FIXTURE,
    run_public_correctness_probe,
)


class FakeBridge:
    def __init__(self, token: int) -> None:
        self.token = token
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        request: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.requests.append({**request, "timeout": timeout})
        return {"token_ids": [self.token]}


class PublicCorrectnessProbeTests(unittest.TestCase):
    def test_compares_one_token_without_stopping_on_fixture_eos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / PUBLIC_FIXTURE
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "name": "public",
                                "prompt_tokens": [10, 11],
                                "expected_tokens": [42, 43],
                            }
                        ]
                    }
                )
            )
            bridge = FakeBridge(42)

            result = run_public_correctness_probe(root, bridge, timeout=12.5)

        self.assertTrue(result["available"])
        self.assertTrue(result["matches_m5_fixture"])
        self.assertEqual(result["expected_token"], 42)
        self.assertEqual(result["actual_token"], 42)
        self.assertEqual(
            bridge.requests,
            [
                {
                    "kind": "generate",
                    "prompt_token_ids": [10, 11],
                    "max_tokens": 1,
                    "temperature": 0,
                    "stop_token_ids": [],
                    "timeout": 12.5,
                }
            ],
        )

    def test_reports_fixture_absence_for_portable_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_public_correctness_probe(
                Path(temporary),
                FakeBridge(1),
                timeout=1,
            )

        self.assertFalse(result["available"])
        self.assertIn("not present", result["reason"])


if __name__ == "__main__":
    unittest.main()
