#!/usr/bin/env python3
import json
import os
import sys


print(
    json.dumps(
        {
            "kind": "ready",
            "ok": True,
            "model": "fake",
            "lm_head_prune": os.environ.get("DARKBLOOM_LM_HEAD_PRUNE"),
            "startup_profile": os.environ.get(
                "DARKBLOOM_STARTUP_MEMORY_PROFILE"
            ),
        }
    ),
    flush=True,
)
for line in sys.stdin:
    request = json.loads(line)
    if request.get("test_protocol") == "wrong_id":
        response = {"id": "wrong", "ok": True, "token_ids": []}
    elif request["kind"] == "generate":
        seed = request.get("seed", 0)
        response = {
            "id": request["id"],
            "ok": True,
            "token_ids": [65 + seed % 26, 24],
            "finish_reason": "stop",
        }
    elif request["kind"] == "logprobs":
        start = request["score_start"]
        end = request["score_end"]
        response = {
            "id": request["id"],
            "ok": True,
            "token_logprobs": [-float(index) for index in range(start, end)],
        }
    else:
        response = {"id": request["id"], "ok": False, "error": "unknown request"}
    print(json.dumps(response), flush=True)
