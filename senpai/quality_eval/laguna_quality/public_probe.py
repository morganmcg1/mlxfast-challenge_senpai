from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PUBLIC_FIXTURE = Path(
    "correctness_prompts/public_longcopy_gate_english_512_256.json"
)


def run_public_correctness_probe(
    checkout: Path,
    bridge: Any,
    *,
    timeout: float,
) -> dict[str, Any]:
    """Compare one candidate token with the checked-in M5 public fixture."""

    fixture = checkout / PUBLIC_FIXTURE
    if not fixture.is_file():
        return {
            "available": False,
            "fixture": str(fixture),
            "reason": "checked-in public fixture is not present in this artifact",
        }

    data = fixture.read_bytes()
    document = json.loads(data)
    cases = document.get("cases") if isinstance(document, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"public correctness fixture has no cases: {fixture}")
    case = cases[0]
    if not isinstance(case, dict):
        raise ValueError(f"public correctness fixture case is not an object: {fixture}")
    prompt = _token_list(case.get("prompt_tokens"), "prompt_tokens", fixture)
    expected = _token_list(case.get("expected_tokens"), "expected_tokens", fixture)

    response = bridge.request(
        {
            "kind": "generate",
            "prompt_token_ids": prompt,
            "max_tokens": 1,
            "temperature": 0,
            "stop_token_ids": [],
        },
        timeout=timeout,
    )
    actual = _token_list(response.get("token_ids"), "token_ids", fixture)
    matches = actual[0] == expected[0]
    return {
        "available": True,
        "fixture": str(fixture),
        "fixture_sha256": hashlib.sha256(data).hexdigest(),
        "case": str(case.get("name") or "case_1"),
        "prompt_token_count": len(prompt),
        "expected_token": expected[0],
        "actual_token": actual[0],
        "matches_m5_fixture": matches,
        "interpretation": (
            "candidate matches the checked-in M5 first-token fixture"
            if matches
            else (
                "candidate diverges from the checked-in M5 fixture on this host; "
                "treat absolute generation scores as diagnostic and use a matched "
                "baseline comparison"
            )
        ),
    }


def _token_list(value: Any, field: str, fixture: Path) -> list[int]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(token, int) or isinstance(token, bool) for token in value)
    ):
        raise ValueError(f"public correctness fixture has invalid {field}: {fixture}")
    return value
