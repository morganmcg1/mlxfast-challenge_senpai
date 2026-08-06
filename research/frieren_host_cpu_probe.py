#!/usr/bin/env python3
"""Direct-worker host-CPU probe for the steady one-token decode step.

Drives `.build-worker/release/mlxfast-runtime-worker` over its JSON protocol,
bypassing the benchmark harness, so a host-CPU measurement costs ~90 s instead
of an ~11 min `--local-iterate` pair. Reports, for a fixed window of steady
decode steps:

  * wall seconds per step (parent-side, includes the JSON round trip)
  * process CPU nanoseconds per step (all threads, proc_pid_rusage)
  * per-thread CPU milliseconds per step (`ps -M`)

Research-only; not part of the submitted surface and not a scored path.
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time

RUSAGE_INFO_V4 = 4
_libc = ctypes.CDLL(None, use_errno=True)
_libc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
_libc.proc_pid_rusage.restype = ctypes.c_int


def proc_cpu_ns(pid):
    buf = ctypes.create_string_buffer(2048)
    if _libc.proc_pid_rusage(pid, RUSAGE_INFO_V4, buf) != 0:
        raise OSError(ctypes.get_errno(), "proc_pid_rusage failed")
    raw = buf.raw
    user = int.from_bytes(raw[16:24], "little")
    system = int.from_bytes(raw[24:32], "little")
    return user, system


def thread_cpu_ms(pid):
    """Per-thread cumulative CPU (system + user) from `ps -M`, milliseconds."""
    out = subprocess.run(
        ["ps", "-M", "-p", str(pid)], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    times = []
    for line in out[1:]:
        stamps = []
        for field in line.split():
            if ":" in field and "." in field:
                mm, rest = field.split(":", 1)
                try:
                    stamps.append(int(mm) * 60_000 + int(round(float(rest) * 1000)))
                except ValueError:
                    pass
        if stamps:
            times.append(sum(stamps[:2]))
    return times


def run_prefill(args, send, proc):
    """Repeated whole-prompt `prefill` requests, each timed individually.

    The worker's `prefill` kind is self-contained: it resets the allocator,
    builds a fresh cache, runs one L=`--seed-tokens` forward and `eval`s the
    logits before replying, so host wall time around the request is the GPU
    prefill time plus a fixed protocol constant. Every repetition uses a
    DIFFERENT prompt, so no identical-forward memo can serve one repetition
    from another; the token values themselves do not change the work.
    """
    n_warm, n_meas = args.warmup_steps, args.measure_steps
    t_load = time.monotonic()
    rid, samples = 1, []
    for rep in range(n_warm + n_meas):
        prompt = [(i * 7919 + rep * 104_729) % 100_000 + 16
                  for i in range(args.seed_tokens)]
        t0 = time.monotonic()
        resp = send({"id": rid, "kind": "prefill", "prompt_tokens": prompt})
        dt = (time.monotonic() - t0) * 1000
        rid += 1
        if rep == 0:
            print(f"[{args.label}] load+first {time.monotonic() - t_load:.1f}s "
                  f"token={resp['token']}", flush=True)
        if rep >= n_warm:
            samples.append(dt)

    samples.sort()
    n = len(samples)
    mean = sum(samples) / n
    var = sum((x - mean) ** 2 for x in samples) / (n - 1) if n > 1 else 0.0
    median = (samples[n // 2] if n % 2
              else (samples[n // 2 - 1] + samples[n // 2]) / 2)
    print(f"[{args.label}] mode=prefill L={args.seed_tokens} n={n} "
          f"prefill_ms_mean={mean:.4f} prefill_ms_sd={var ** 0.5:.4f} "
          f"prefill_ms_median={median:.4f} prefill_ms_min={samples[0]:.4f}",
          flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-tokens", type=int, default=512)
    ap.add_argument("--warmup-steps", type=int, default=100)
    ap.add_argument("--measure-steps", type=int, default=400)
    ap.add_argument("--sample-seconds", type=int, default=0,
                    help="if >0, run macOS `sample` on the worker during the "
                         "measure window and write the profile here")
    ap.add_argument("--sample-out", default="/tmp/frieren_worker_sample.txt")
    ap.add_argument("--label", default="arm")
    ap.add_argument("--mode", choices=("decode", "prefill"), default="decode",
                    help="decode: steady one-token steps. prefill: repeated "
                         "whole-prompt `prefill` requests at --seed-tokens.")
    args = ap.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    worker = os.path.join(repo, ".build-worker/release/mlxfast-runtime-worker")
    if not os.path.exists(worker):
        sys.exit(f"worker binary missing: {worker}")

    env = dict(os.environ)
    proc = subprocess.Popen(
        [worker, "runtime-worker", "--weights", "weights"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        cwd=repo, env=env,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("worker closed the protocol stream")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise SystemExit(f"worker error: {resp}")
        return resp

    hello = json.loads(proc.stdout.readline())
    assert hello.get("ok"), hello

    if args.mode == "prefill":
        run_prefill(args, send, proc)
        proc.stdin.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
        return

    t_load = time.monotonic()
    # Deterministic pseudo-realistic seed: spread over the vocabulary so expert
    # routing is not degenerate. Values are irrelevant to host-side cost.
    seed = [(i * 7919) % 100_000 + 16 for i in range(args.seed_tokens)]
    resp = send({"id": 1, "kind": "decode_begin", "seed_tokens": seed})
    token = resp["seed_token"]
    print(f"[{args.label}] load+seed {time.monotonic() - t_load:.1f}s "
          f"seed_token={token}", flush=True)

    rid = 2
    for _ in range(args.warmup_steps):
        token = send({"id": rid, "kind": "decode_step", "token": token})["token"]
        rid += 1

    sampler = None
    if args.sample_seconds > 0:
        sampler = subprocess.Popen(
            ["sample", str(proc.pid), str(args.sample_seconds), "1",
             "-file", args.sample_out],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )

    threads_before = thread_cpu_ms(proc.pid)
    u0, s0 = proc_cpu_ns(proc.pid)
    w0 = time.monotonic()
    for _ in range(args.measure_steps):
        token = send({"id": rid, "kind": "decode_step", "token": token})["token"]
        rid += 1
    w1 = time.monotonic()
    u1, s1 = proc_cpu_ns(proc.pid)
    threads_after = thread_cpu_ms(proc.pid)

    if sampler is not None:
        sampler.wait()

    n = args.measure_steps
    wall_ms = (w1 - w0) * 1000 / n
    user_ms = (u1 - u0) / 1e6 / n
    sys_ms = (s1 - s0) / 1e6 / n
    print(f"[{args.label}] steps={n} wall_ms_per_step={wall_ms:.4f} "
          f"cpu_user_ms_per_step={user_ms:.4f} cpu_sys_ms_per_step={sys_ms:.4f} "
          f"cpu_total_ms_per_step={user_ms + sys_ms:.4f} "
          f"cpu_over_wall={(user_ms + sys_ms) / wall_ms:.3f}", flush=True)
    per_thread = []
    for i, after in enumerate(threads_after):
        before = threads_before[i] if i < len(threads_before) else 0
        per_thread.append(round((after - before) / n, 4))
    print(f"[{args.label}] per_thread_cpu_ms_per_step={per_thread}", flush=True)

    proc.stdin.close()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.terminate()


if __name__ == "__main__":
    main()
