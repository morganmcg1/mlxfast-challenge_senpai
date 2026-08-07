#!/usr/bin/env python3
"""Research-only driver for the compiled-elementwise-fusion price probe.

Runs one teacher-forced decode phase against the already-built runtime worker
and writes a JSON record with per-step wall times and the full generated token
sequence, so two arms can be compared for both latency and bit-exactness.

  python3 research/nezuko_compile_probe.py --steps 200 --out /tmp/arm.json

Every model-holding run must be the only one on the host.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)


def mach_now() -> float:
    return time.clock_gettime(time.CLOCK_UPTIME_RAW)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--stderr", default="/tmp/nezuko_compile_probe.err")
    ap.add_argument("--weights", default="weights")
    args = ap.parse_args()

    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt = case["prompt_tokens"]
    expected = case["expected_tokens"]

    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    errfh = open(args.stderr, "wb")
    proc = subprocess.Popen(
        [WORKER, "runtime-worker", "--weights", args.weights],
        cwd=REPO,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=errfh,
        env=env,
        bufsize=1,
        text=True,
    )

    def send(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("worker closed stdout; see " + args.stderr)
        resp = json.loads(line)
        if not resp.get("ok", False):
            raise SystemExit("worker error: " + json.dumps(resp))
        return resp

    json.loads(proc.stdout.readline())
    send({"id": 2, "kind": "decode_begin", "seed_tokens": prompt})

    step_ms = []
    produced = []
    token = expected[0]
    for i in range(args.steps):
        t0 = mach_now()
        resp = send({"id": 100 + i, "kind": "decode_step", "token": token})
        step_ms.append((mach_now() - t0) * 1e3)
        produced.append(resp["token"])
        token = expected[i + 1] if i + 1 < len(expected) else resp["token"]

    proc.stdin.close()
    proc.wait(timeout=120)
    errfh.close()

    steady = step_ms[1:]
    record = {
        "label": args.label,
        "steps": args.steps,
        "step_ms": step_ms,
        "produced_tokens": produced,
        "golden_divergences": sum(
            1
            for i, t in enumerate(produced)
            if i + 1 < len(expected) and t != expected[i + 1]
        ),
        "mean_ms": statistics.mean(steady),
        "median_ms": statistics.median(steady),
        "env": {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("DARKBLOOM_", "MLX_"))
        },
    }
    with open(args.out, "w") as fh:
        json.dump(record, fh)
    print(
        f"{args.label}: mean={record['mean_ms']:.4f} ms "
        f"median={record['median_ms']:.4f} ms "
        f"golden_divergences={record['golden_divergences']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
