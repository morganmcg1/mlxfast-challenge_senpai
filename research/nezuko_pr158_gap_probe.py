#!/usr/bin/env python3
"""Research-only decode dead-time decomposition probe (PR #158, not submitted).

`decode_probe.py` reports gap = wall - gpu_busy_union, where `wall` is the
Python->worker->Python JSON round trip for one `decode_step`. That gap has three
structurally different components:

  1. request/response IPC (pipe write, wake, JSON encode/decode on both sides)
  2. host-side MLX graph build + command encoding + eval wait inside the worker
  3. GPU idle between command buffers

Only (2) and (3) are addressable by editable code. This probe measures (1)
directly by timing round trips of an unknown request kind, which the trusted
worker answers with ok:false from its dispatch default case without touching the
model or the GPU (LagunaRuntimeWorker.swift:474-476, error path at :78-86).

Usage (must be the only model-holding process on the host):

  python3 research/nezuko_pr158_gap_probe.py --steps 200 --pings 400 \
      [--profile] [--stderr /tmp/w.err]
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research"))
from decode_probe import analyze_profile  # noqa: E402

WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)


def stats(label, samples):
    ordered = sorted(samples)
    n = len(ordered)
    print(
        f"{label}: n={n} "
        f"mean={statistics.mean(ordered)*1e6:.1f} us "
        f"median={statistics.median(ordered)*1e6:.1f} us "
        f"p10={ordered[n//10]*1e6:.1f} us "
        f"p90={ordered[9*n//10]*1e6:.1f} us "
        f"min={ordered[0]*1e6:.1f} us max={ordered[-1]*1e6:.1f} us",
        flush=True,
    )
    return statistics.median(ordered)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--pings", type=int, default=400)
    ap.add_argument("--stderr", default="/tmp/nezuko-pr158-gap.err")
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--profile-top", type=int, default=44)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt = case["prompt_tokens"]
    expected = case["expected_tokens"]

    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    errfh = open(args.stderr, "wb")
    t_launch = time.perf_counter()
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

    def raw(req):
        """One round trip; returns (response, elapsed) and tolerates ok:false."""
        t0 = time.perf_counter()
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        dt = time.perf_counter() - t0
        if not line:
            raise SystemExit("worker closed stdout; see " + args.stderr)
        return json.loads(line), dt

    def send(req):
        resp, dt = raw(req)
        if not resp.get("ok", False):
            raise SystemExit("worker error: " + json.dumps(resp))
        return resp, dt

    json.loads(proc.stdout.readline())
    print(f"[{args.label}] worker up in {time.perf_counter()-t_launch:.1f}s",
          flush=True)

    def ping_floor(tag, n):
        spans = []
        for i in range(n):
            resp, dt = raw({"id": 700000 + i, "kind": "nezuko_ipc_floor_ping"})
            if resp.get("ok", True):
                raise SystemExit("expected ok:false for unknown kind")
            spans.append(dt)
        return stats(f"[{args.label}] ipc_floor {tag}", spans[1:])

    ipc_before = ping_floor("before_decode", args.pings)

    _, seed_dt = send({"id": 2, "kind": "decode_begin", "seed_tokens": prompt})
    print(f"[{args.label}] decode_begin seed forward: {seed_dt*1e3:.2f} ms",
          flush=True)

    step_spans = []
    mismatches = []
    token = expected[0]
    for i in range(args.steps):
        t0 = time.perf_counter()
        resp, _ = send({"id": 100 + i, "kind": "decode_step", "token": token})
        step_spans.append((t0, time.perf_counter()))
        if i + 1 < len(expected) and resp["token"] != expected[i + 1]:
            mismatches.append((i, expected[i + 1], resp["token"]))
        token = expected[i + 1] if i + 1 < len(expected) else resp["token"]
    print(f"[{args.label}] teacher-forced: {len(mismatches)} divergences"
          + (f" first={mismatches[0]}" if mismatches else " (all match)"),
          flush=True)

    steady = [b - a for a, b in step_spans[1:]]
    wall_median = stats(f"[{args.label}] decode_step wall", steady)

    ipc_after = ping_floor("after_decode", args.pings)

    ipc = min(ipc_before, ipc_after)
    print(f"[{args.label}] SUMMARY wall_median={wall_median*1e3:.3f} ms "
          f"ipc_floor_median={ipc*1e6:.1f} us "
          f"ipc_share_of_wall={ipc/wall_median*100:.2f}%", flush=True)

    proc.stdin.close()
    proc.wait(timeout=180)
    errfh.close()

    if args.profile:
        analyze_profile(args.stderr, step_spans, args.profile_top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
