#!/usr/bin/env python3
"""PR #80 bitwise logit certificate driver (research-only, not submitted).

Why this instrument. The greedy-token gate is blind to coherent displacement of
the attention scale plane: `research/frieren-pr35-r4-gate-blindness.md` records a
sweep that faulted 72-75% of 389,120 rows at mean relative error 0.2311 with ZERO
token changes. A passing token gate is therefore not evidence for a scale-plane
re-encoding. The upstream-equivalence oracle is also unusable here: it never
calls `prepareFusedRuntimeWeights()`, so the derived banks stay nil inside it.

The instrument that does reach the banks is the runtime worker's teacher-forced
`correctness_begin`/`correctness_step` protocol. Those two requests run the real
`LagunaRuntimeModel` forward over the real prepared weights, and when paired with
`top_k` + `expected_token` they return the exact Float32 logit values (widened to
Double) rather than only an argmax. Requesting the full vocabulary turns each
decode step into a complete, bit-resolved fingerprint of the model output.

READOUT: one SHA-256 per step over the canonical (token, logit-bit-pattern) list,
plus a whole-run digest. Two arms of the same binary that dispatch different
scale planes must produce byte-identical digests. Any difference -- even one ULP
in one logit of one step -- changes the digest.

  python3 research/frieren_pr80_logit_bitwise.py --label ref --steps 64 \
      --out /tmp/pr80_cert/ref.json

Environment reaches the worker unchanged, so the caller selects the arm with the
DARKBLOOM_* switches. Every model-holding run must be the only one on the host.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)
VOCAB_SIZE = 100_352

# Dispatch-log lines the worker emits under DARKBLOOM_ATTN_SCALE_NARROW_LOG=1.
# Captured so plane reachability is witnessed directly instead of inferred.
DISPATCH_RE = re.compile(
    r"(lane-major[^\n]*|narrow-scales[^\n]*|declined[^\n]*|inactive[^\n]*|escaped[^\n]*)"
)


def step_digest(top_logits):
    """Canonical, lossless digest of one step's returned logit list.

    `struct.pack('>d')` keeps the exact bit pattern, so two arms agreeing here
    agree on every bit of every returned logit, not merely on a printed form.
    """
    h = hashlib.sha256()
    for entry in top_logits:
        h.update(struct.pack(">iq", entry["token"], 0))
        h.update(struct.pack(">d", entry["logit"]))
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--steps", type=int, default=64)
    ap.add_argument("--top-k", type=int, default=VOCAB_SIZE)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stderr", default=None)
    ap.add_argument("--weights", default="weights")
    args = ap.parse_args()

    if not os.path.exists(WORKER):
        print(f"missing worker binary {WORKER}; build with ./benchmark.sh --local-iterate")
        return 2

    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt = case["prompt_tokens"]
    expected = case["expected_tokens"]
    if args.steps > len(expected) - 1:
        args.steps = len(expected) - 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    err_path = args.stderr or (os.path.splitext(args.out)[0] + ".worker.err")
    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    env["DARKBLOOM_ATTN_SCALE_NARROW_LOG"] = "1"

    t_launch = time.perf_counter()
    with open(err_path, "wb") as errfh:
        proc = subprocess.Popen(
            [WORKER, "runtime-worker", "--weights", args.weights],
            cwd=REPO,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errfh,
            env=env,
            text=True,
        )

        def send(req):
            proc.stdin.write(json.dumps(req) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise SystemExit(f"worker closed stdout; see {err_path}")
            resp = json.loads(line)
            if not resp.get("ok", False):
                raise SystemExit("worker error: " + json.dumps(resp)[:2000])
            return resp

        hello = json.loads(proc.stdout.readline())
        print(
            f"[{args.label}] worker up in {time.perf_counter() - t_launch:.1f}s "
            f"ok={hello.get('ok')} top_k={args.top_k} steps={args.steps}",
            flush=True,
        )

        steps = []
        token_stream = []
        resp = send(
            {
                "id": 1,
                "kind": "correctness_begin",
                "prompt_tokens": prompt,
                "top_k": args.top_k,
                "expected_token": expected[0],
            }
        )
        steps.append(
            {
                "step": 0,
                "kind": "begin",
                "token": resp["token"],
                "expected": expected[0],
                "returned": len(resp["top_logits"]),
                "digest": step_digest(resp["top_logits"]),
                "expected_token_logit": resp.get("expected_token_logit"),
                "top_logit_margin": resp.get("top_logit_margin"),
            }
        )
        token_stream.append(resp["token"])

        for i in range(args.steps):
            resp = send(
                {
                    "id": 2 + i,
                    "kind": "correctness_step",
                    "token": expected[i],
                    "top_k": args.top_k,
                    "expected_token": expected[i + 1],
                }
            )
            steps.append(
                {
                    "step": i + 1,
                    "kind": "step",
                    "token": resp["token"],
                    "expected": expected[i + 1],
                    "returned": len(resp["top_logits"]),
                    "digest": step_digest(resp["top_logits"]),
                    "expected_token_logit": resp.get("expected_token_logit"),
                    "top_logit_margin": resp.get("top_logit_margin"),
                }
            )
            token_stream.append(resp["token"])

        proc.stdin.close()
        proc.wait(timeout=120)

    run_digest = hashlib.sha256(
        "".join(s["digest"] for s in steps).encode()
    ).hexdigest()
    token_mismatches = sum(
        1 for s in steps if s["kind"] == "step" and s["token"] != s["expected"]
    ) + (1 if steps[0]["token"] != steps[0]["expected"] else 0)

    with open(err_path, "r", errors="replace") as fh:
        dispatch = sorted(set(DISPATCH_RE.findall(fh.read())))

    report = {
        "label": args.label,
        "env": {
            k: v for k, v in sorted(os.environ.items()) if k.startswith("DARKBLOOM_")
        },
        "top_k": args.top_k,
        "steps": steps,
        "run_digest": run_digest,
        "token_stream": token_stream,
        "token_mismatches": token_mismatches,
        "dispatch_witness": dispatch,
    }
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1)

    print(f"[{args.label}] RUN_DIGEST {run_digest}", flush=True)
    print(f"[{args.label}] TOKEN_MISMATCHES {token_mismatches}", flush=True)
    for line in dispatch:
        print(f"[{args.label}] DISPATCH {line}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
