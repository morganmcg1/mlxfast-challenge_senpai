#!/usr/bin/env python3
"""Research-only decode/prefill probe driver (not part of the submission).

Drives the already-built runtime worker over its line-delimited JSON protocol so
a pure decode phase can be profiled without the full benchmark harness.

  python3 research/decode_probe.py --steps 200 [--prefill] [--stderr /tmp/w.err]

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


def rss_gb(pid: int) -> float:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)],
                         capture_output=True, text=True).stdout.strip()
    return int(out) * 1024 / 2**30 if out else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--prefill", action="store_true", help="also time one 512-token prefill")
    ap.add_argument("--stderr", default="/tmp/decode_probe.worker.err")
    ap.add_argument("--weights", default="weights")
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

    hello = json.loads(proc.stdout.readline())
    load_seconds = time.perf_counter() - t_launch
    print(f"worker up in {load_seconds:.1f}s ok={hello.get('ok')}", flush=True)

    def report_diagnostics(label: str, req_id: int) -> None:
        diag = send({"id": req_id, "kind": "phase_diagnostics"})
        print(f"diagnostics {label}: "
              f"worker_rss_gb={rss_gb(proc.pid):.2f} "
              f"peak_ram_gb={diag.get('peak_ram_gb')} "
              f"mlx_active_gb={(diag.get('mlx_active_memory_bytes') or 0)/2**30:.2f} "
              f"mlx_cache_gb={(diag.get('mlx_cache_memory_bytes') or 0)/2**30:.2f} "
              f"mlx_peak_gb={(diag.get('mlx_peak_memory_bytes') or 0)/2**30:.2f}",
              flush=True)

    report_diagnostics("after load", 900)

    if args.prefill:
        t0 = time.perf_counter()
        send({"id": 1, "kind": "prefill", "prompt_tokens": prompt})
        dt = time.perf_counter() - t0
        print(f"prefill 512 tokens: {dt*1e3:.2f} ms "
              f"({dt/len(prompt)*1e6:.1f} us/token)", flush=True)

    t0 = time.perf_counter()
    send({"id": 2, "kind": "decode_begin", "seed_tokens": prompt})
    seed_dt = time.perf_counter() - t0
    print(f"decode_begin seed forward: {seed_dt*1e3:.2f} ms", flush=True)

    step_times = []
    token = expected[0]
    print("DECODE_PHASE_START", flush=True)
    for i in range(args.steps):
        t0 = time.perf_counter()
        resp = send({"id": 100 + i, "kind": "decode_step", "token": token})
        step_times.append(time.perf_counter() - t0)
        token = expected[i + 1] if i + 1 < len(expected) else resp["token"]
    print("DECODE_PHASE_END", flush=True)

    print("first 8 steps (ms): "
          + " ".join(f"{t*1e3:.3f}" for t in step_times[:8]), flush=True)
    ordered = sorted(step_times)
    print(f"decode steps={len(step_times)} "
          f"mean={statistics.mean(step_times)*1e3:.3f} ms "
          f"median={statistics.median(step_times)*1e3:.3f} ms "
          f"p10={ordered[len(ordered)//10]*1e3:.3f} ms "
          f"p90={ordered[9*len(ordered)//10]*1e3:.3f} ms "
          f"min={ordered[0]*1e3:.3f} ms max={ordered[-1]*1e3:.3f} ms "
          f"total={sum(step_times):.3f} s", flush=True)

    report_diagnostics("after decode", 901)

    proc.stdin.close()
    proc.wait(timeout=120)
    errfh.close()
    print(f"worker stderr -> {args.stderr}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
