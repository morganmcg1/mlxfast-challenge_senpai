#!/usr/bin/env python3
"""R128-D driver: repeated steady-decode wall measurement with span capture.

Research-only. Same worker protocol and same golden as research/decode_probe.py
so its wall step is directly comparable, but it launches the worker `--runs`
times, records the absolute mach span of every decode step, and brackets the
decode phase with a null-request round-trip census so the driver's own protocol
cost can be subtracted from the wall-vs-busy residual.

  DECODE_PROBE_WORKER=/tmp/w-clean python3 research/alphonse-r128d-probe.py \
      --runs 6 --steps 400 --out /tmp/r128d-clean.json

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
WORKER = os.environ.get("DECODE_PROBE_WORKER") or os.path.join(
    REPO, ".build-worker/release/mlxfast-runtime-worker"
)
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)


def mach_now() -> float:
    """Seconds on the same epoch as `MTLCommandBuffer.GPUStartTime`."""
    return time.clock_gettime(time.CLOCK_UPTIME_RAW)


def one_run(idx: int, args, prompt, expected):
    errpath = f"{args.stderr_prefix}.{idx}.err"
    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    errfh = open(errpath, "wb")
    t_launch = mach_now()
    proc = subprocess.Popen(
        [WORKER, "runtime-worker", "--weights", args.weights],
        cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=errfh, env=env, bufsize=1, text=True,
    )

    def send(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("worker closed stdout; see " + errpath)
        resp = json.loads(line)
        if not resp.get("ok", False):
            raise SystemExit("worker error: " + json.dumps(resp))
        return resp

    json.loads(proc.stdout.readline())
    load_s = mach_now() - t_launch

    def rtt_census(base_id: int, n: int):
        out = []
        for i in range(n):
            t0 = mach_now()
            send({"id": base_id + i, "kind": "phase_diagnostics"})
            out.append(mach_now() - t0)
        return out

    rtt_pre = rtt_census(1000, args.rtt)

    t0 = mach_now()
    send({"id": 2, "kind": "decode_begin", "seed_tokens": prompt})
    seed_s = mach_now() - t0

    spans = []
    mismatches = 0
    token = expected[0]
    for i in range(args.steps):
        a = mach_now()
        resp = send({"id": 100 + i, "kind": "decode_step", "token": token})
        spans.append((a, mach_now()))
        if i + 1 < len(expected):
            if resp["token"] != expected[i + 1]:
                mismatches += 1
            token = expected[i + 1]
        else:
            token = resp["token"]

    rtt_post = rtt_census(5000, args.rtt)
    proc.stdin.close()
    proc.wait(timeout=120)
    errfh.close()

    steady = [b - a for a, b in spans[1:]]
    med = statistics.median(steady)
    print(f"run {idx}: load={load_s:.1f}s seed={seed_s*1e3:.2f}ms "
          f"median_step={med*1e6:.1f}us n={len(steady)} "
          f"rtt_pre_med={statistics.median(rtt_pre)*1e6:.1f}us "
          f"rtt_post_med={statistics.median(rtt_post)*1e6:.1f}us "
          f"mismatches={mismatches}", flush=True)
    return {
        "idx": idx, "stderr": errpath, "load_s": load_s, "seed_s": seed_s,
        "spans": spans, "rtt_pre": rtt_pre, "rtt_post": rtt_post,
        "mismatches": mismatches,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--rtt", type=int, default=200)
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--stderr-prefix", default="/tmp/r128d.worker")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt, expected = case["prompt_tokens"], case["expected_tokens"]

    runs = [one_run(i, args, prompt, expected) for i in range(args.runs)]
    meds = [statistics.median([b - a for a, b in r["spans"][1:]]) for r in runs]
    ordered = sorted(meds)
    print(f"\nACROSS RUNS n={len(meds)} "
          f"median={statistics.median(meds)*1e6:.1f}us "
          f"min={ordered[0]*1e6:.1f} max={ordered[-1]*1e6:.1f} "
          + (f"sd={statistics.stdev(meds)*1e6:.1f}us" if len(meds) > 1 else ""),
          flush=True)
    with open(args.out, "w") as fh:
        json.dump({"worker": WORKER, "steps": args.steps, "runs": runs,
                   "env": {k: v for k, v in os.environ.items()
                           if k.startswith("DARKBLOOM")}}, fh)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
