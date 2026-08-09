"""Dump the full official receipt row for one submission id.

The per-submission endpoint does not return JSON, so this reads the account
submission list feed and selects the exact row.
"""

import importlib.util
import json
import os
import sys

SPEC = importlib.util.spec_from_file_location(
    "watch_submission", os.path.join(os.path.dirname(__file__), "..", "senpai", "watch-submission.py")
)
watch = importlib.util.module_from_spec(SPEC)
sys.modules["watch_submission"] = watch  # dataclass resolution needs the module registered
SPEC.loader.exec_module(watch)


def main() -> int:
    submission_id = sys.argv[1]
    benchmark_ref = sys.argv[2] if len(sys.argv) > 2 else "eigenlabs/mlxfast-challenge"

    client = watch.ApiClient(watch.load_api_config())
    account_id, benchmark_id = watch.resolve_scope(client, benchmark_ref)

    rows = watch.account_submissions(client, (account_id, benchmark_id))
    match = next((row for row in rows if str(row.get("id")) == submission_id), None)
    if match is None:
        print(json.dumps({"error": "submission not found in feed", "rows": len(rows)}))
        return 1

    print(json.dumps(match, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
