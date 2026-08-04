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
    ap.add_argument("--profile", action="store_true",
                    help="parse GPUPROF records from the worker stderr and "
                         "attribute GPU time to the steady decode window")
    ap.add_argument("--profile-top", type=int, default=40)
    ap.add_argument("--golden", default=GOLDEN)
    args = ap.parse_args()

    with open(args.golden) as fh:
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

    step_spans = []
    mismatches = []
    token = expected[0]
    print("DECODE_PHASE_START", flush=True)
    for i in range(args.steps):
        t0 = time.perf_counter()
        resp = send({"id": 100 + i, "kind": "decode_step", "token": token})
        step_spans.append((t0, time.perf_counter()))
        if i + 1 < len(expected) and resp["token"] != expected[i + 1]:
            mismatches.append((i, expected[i + 1], resp["token"]))
        token = expected[i + 1] if i + 1 < len(expected) else resp["token"]
    print("DECODE_PHASE_END", flush=True)
    print(f"teacher-forced greedy tokens: {len(mismatches)} divergences"
          + (f" first={mismatches[0]}" if mismatches else " (all match)"),
          flush=True)
    step_times = [b - a for a, b in step_spans]

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

    if args.profile:
        analyze_profile(args.stderr, step_spans, args.profile_top)
    return 0


def analyze_profile(err_path: str, step_spans, top: int) -> None:
    """Attribute GPUPROF command-buffer records to the steady decode window.

    MTLCommandBuffer.GPUStartTime and time.perf_counter share the mach
    absolute-time epoch on macOS, so the driver's per-step wall spans window
    the GPU records directly.
    """
    records = []
    with open(err_path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            _, start, end, nops, names = line.rstrip("\n").split(" ", 4)
            records.append((float(start), float(end), int(nops), names))
    if not records:
        print("profile: no GPUPROF records (was DARKBLOOM_GPU_PROFILE=1 set?)")
        return

    # Skip step 0: it pays the one-time KV growth concat on full-attention layers.
    steady = step_spans[1:]
    lo, hi = steady[0][0], steady[-1][1]
    wall = sum(b - a for a, b in steady)
    window = [r for r in records if r[0] >= lo and r[1] <= hi]
    print(f"\nprofile: {len(records)} command buffers total, "
          f"{len(window)} inside {len(steady)} steady steps")
    if not window:
        return

    busy = sum(e - s for s, e, _, _ in window)
    merged = 0.0
    cur_s, cur_e = window[0][0], window[0][1]
    for s, e, _, _ in sorted(window)[1:]:
        if s > cur_e:
            merged += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    merged += cur_e - cur_s
    dispatches = sum(r[2] for r in window)
    n = len(steady)
    print(f"per steady step: wall={wall/n*1e3:.3f} ms "
          f"gpu_busy_sum={busy/n*1e3:.3f} ms "
          f"gpu_busy_union={merged/n*1e3:.3f} ms "
          f"gap={(wall-merged)/n*1e3:.3f} ms "
          f"({(wall-merged)/wall*100:.1f}% of wall) "
          f"cbs={len(window)/n:.1f} dispatches={dispatches/n:.1f}")

    agg = {}
    for s, e, nops, names in window:
        key = "|".join(shorten(p) for p in names.split("|"))
        if nops > 1:
            key = f"[{nops}] {key}"
        c, t = agg.get(key, (0, 0.0))
        agg[key] = (c + 1, t + (e - s))
    rows = sorted(agg.items(), key=lambda kv: -kv[1][1])
    print(f"\n{'us/step':>9} {'share':>7} {'n/step':>7} {'us/call':>8}  kernel")
    for key, (count, total) in rows[:top]:
        print(f"{total/n*1e6:9.1f} {total/busy*100:6.2f}% "
              f"{count/n:7.2f} {total/count*1e6:8.2f}  {key}")
    tail = sum(t for _, (_, t) in rows[top:])
    if tail:
        print(f"{tail/n*1e6:9.1f} {tail/busy*100:6.2f}% "
              f"{'':>7} {'':>8}  ... {len(rows)-top} more")


MANGLE_MARKERS = ("_bfloat16_t", "_uint32_t", "_uint8_t", "_uint16_t",
                  "_int32_t", "_int64_t", "_float", "_bool")


def shorten(name: str) -> str:
    """Drop MLX's trailing template type mangling and the common prefix."""
    name = name.removeprefix("custom_kernel_laguna_")
    cut = min((i for i in (name.find(m) for m in MANGLE_MARKERS) if i > 0),
              default=-1)
    return name[:cut] if cut > 0 else name


if __name__ == "__main__":
    sys.exit(main())
