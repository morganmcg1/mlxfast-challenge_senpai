#!/usr/bin/env python3
"""Research-only driver + per-dispatch analyzer for the 512-token prefill forward.

Companion to research/decode_probe.py, which only ever profiles steady decode
steps (it drops the seed forward and step 0 from its window). This script
profiles the scored `prefill` request instead: one cold-cache 512-token forward
per request, which is exactly the shape of the scored prefill axis and of the
seed forward charged into the decode figure.

Requires the LOCAL-ONLY GPUPROF hooks in the vendored MLX
backend/metal/device.cpp|.h (env DARKBLOOM_GPU_PROFILE=1, optionally
DARKBLOOM_GPU_PROFILE_SPLIT=1 for one command buffer per primitive). Those hooks
are reverted before any timing run.

Usage:
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/prefill_probe.py --reps 6 --profile --profile-top 40
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKER = REPO / ".build-worker/release/mlxfast-runtime-worker"
GOLDEN = REPO / "correctness_prompts/public_longcopy_gate_english_512_256.json"


def load_prompt():
    case = json.loads(GOLDEN.read_text())["cases"][0]
    return case["prompt_tokens"]


def send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise SystemExit("worker closed stdout")
    resp = json.loads(line)
    if not resp.get("ok"):
        raise SystemExit(f"worker error: {resp}")
    return resp


def shorten(name):
    name = re.sub(r"^custom_kernel_laguna_", "laguna_", name)
    name = re.sub(r"_(float16|bfloat16|float32)_t?(_.*)?$", "", name)
    return name[:78]


FAMILIES = (
    ("routed_gather_gemm", r"gather_qmm|gather_mm"),
    ("dense_qmm_nvfp4", r"^nvfp4_qmm|qmm_splitk|^nvfp4_qvm|quantized_matmul"),
    ("steel_gemm_bf16", r"steel_gemm|^gemm_"),
    ("attention_core", r"attention|sdpa|steel_attn"),
    ("qk_norm_rope", r"qk_norm|rope|yarn"),
    ("router", r"router|topk|top8|tournament"),
    ("moe_tail", r"moe_tail"),
    ("sort_scatter", r"sort|scatter|gather_axis|arange|partition"),
    ("rms_norm", r"rms"),
    ("lm_head", r"lmhead|lm_head"),
    ("elementwise", r"binary|unary|copy|reduce|softmax|concat|slice|pad|fill|"
                    r"broadcast|astype|mul|add|silu|softplus"),
)


def family(short):
    low = short.lower()
    for label, pattern in FAMILIES:
        if re.search(pattern, low):
            return label
    return "other"


def parse_gpuprof(path):
    """Return list of (gpu_start, gpu_end, nops, bytes, [names])."""
    records = []
    with open(path, "r", errors="replace") as handle:
        for line in handle:
            if not line.startswith("GPUPROF "):
                continue
            parts = line.split(" ", 5)
            if len(parts) < 6:
                continue
            try:
                start = float(parts[1])
                end = float(parts[2])
                nops = int(parts[3])
                nbytes = int(parts[4])
            except ValueError:
                continue
            names = parts[5].strip().split("|") if parts[5].strip() else []
            records.append((start, end, nops, nbytes, names))
    return records


def analyze(records, spans, ceiling_gbs, top_n, label):
    if not records:
        print("profile: no GPUPROF records (was DARKBLOOM_GPU_PROFILE=1 set?)")
        return
    lo, hi = spans[0][0], spans[-1][1]
    window = [r for r in records if r[0] >= lo and r[1] <= hi]
    n_fwd = len(spans)
    wall = sum(b - a for a, b in spans)
    print(f"\nprofile [{label}]: {len(records)} command buffers total, "
          f"{len(window)} inside {n_fwd} forward(s)")
    if not window:
        print("profile: no records inside the measured windows -- timebase "
              "mismatch between MTLCommandBuffer GPU times and perf_counter")
        return

    busy_sum = sum(e - s for s, e, _, _, _ in window)
    merged = []
    for s, e, _, _, _ in sorted(window):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    busy_union = sum(e - s for s, e in merged)
    dispatches = sum(r[2] for r in window)
    total_bytes = sum(r[3] for r in window)

    print(f"  wall            {wall / n_fwd * 1e3:9.3f} ms/forward")
    print(f"  gpu busy (sum)  {busy_sum / n_fwd * 1e3:9.3f} ms/forward "
          f"({busy_sum / wall * 100:.1f}% of wall)")
    print(f"  gpu busy (union){busy_union / n_fwd * 1e3:9.3f} ms/forward "
          f"({busy_union / wall * 100:.1f}% of wall)")
    print(f"  command buffers {len(window) / n_fwd:9.1f} /forward")
    print(f"  dispatches      {dispatches / n_fwd:9.1f} /forward")
    print(f"  bound bytes     {total_bytes / n_fwd / 2**30:9.3f} GiB/forward "
          f"(unique buffers per command buffer)")

    agg = {}
    for s, e, nops, nbytes, names in window:
        key = shorten(names[0]) if len(names) == 1 else (
            "+".join(sorted({shorten(n) for n in names}))[:78] or "empty")
        slot = agg.setdefault(key, [0, 0.0, 0])
        slot[0] += max(1, len(names))
        slot[1] += e - s
        slot[2] += nbytes

    rows = sorted(agg.items(), key=lambda kv: -kv[1][1])
    print(f"\n  {'dispatch':<62} {'n/fwd':>6} {'us/call':>8} {'ms/fwd':>8} "
          f"{'%fwd':>6} {'MB/call':>8} {'GB/s':>7} {'%bw':>5} {'family':>18}")
    for name, (count, seconds, nbytes) in rows[:top_n]:
        per_fwd = seconds / n_fwd
        calls = count / n_fwd
        us_call = seconds / count * 1e6
        mb_call = nbytes / count / 2**20
        gbs = (nbytes / seconds) / 1e9 if seconds > 0 else 0.0
        print(f"  {name:<62} {calls:6.1f} {us_call:8.1f} {per_fwd * 1e3:8.3f} "
              f"{per_fwd / (wall / n_fwd) * 100:6.1f} {mb_call:8.3f} "
              f"{gbs:7.1f} {gbs / ceiling_gbs * 100:5.0f} {family(name):>18}")
    if len(rows) > top_n:
        tail = sum(v[1] for _, v in rows[top_n:]) / n_fwd
        print(f"  {'... ' + str(len(rows) - top_n) + ' more':<62} "
              f"{'':>6} {'':>8} {tail * 1e3:8.3f}")

    fam = {}
    for name, (count, seconds, nbytes) in rows:
        slot = fam.setdefault(family(name), [0, 0.0, 0])
        slot[0] += count
        slot[1] += seconds
        slot[2] += nbytes
    print(f"\n  {'family':<20} {'n/fwd':>7} {'ms/fwd':>8} {'%fwd':>6} "
          f"{'GB/s':>7}")
    for label_, (count, seconds, nbytes) in sorted(
            fam.items(), key=lambda kv: -kv[1][1]):
        per_fwd = seconds / n_fwd
        gbs = (nbytes / seconds) / 1e9 if seconds > 0 else 0.0
        print(f"  {label_:<20} {count / n_fwd:7.1f} {per_fwd * 1e3:8.3f} "
              f"{per_fwd / (wall / n_fwd) * 100:6.1f} {gbs:7.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=6,
                    help="prefill requests to issue (first is discarded)")
    ap.add_argument("--decode-steps", type=int, default=0,
                    help="also run decode_begin + N steps after the prefills")
    ap.add_argument("--weights", default=str(REPO / "weights"))
    ap.add_argument("--stderr", default="/tmp/prefill_probe.worker.err")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--profile-top", type=int, default=40)
    ap.add_argument("--ceiling-gbs", type=float, default=260.2,
                    help="measured host read-bandwidth ceiling, GB/s")
    args = ap.parse_args()

    prompt = load_prompt()
    print(f"prompt tokens: {len(prompt)}")
    err = open(args.stderr, "w")
    proc = subprocess.Popen(
        [str(WORKER), "runtime-worker", "--weights", args.weights],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)

    t0 = time.perf_counter()
    hello = json.loads(proc.stdout.readline())
    if not hello.get("ok"):
        raise SystemExit(f"worker hello failed: {hello}")
    print(f"load: {time.perf_counter() - t0:.1f} s")

    send(proc, {"id": 900, "kind": "phase_diagnostics"})

    spans = []
    tokens = []
    for i in range(args.reps):
        a = time.perf_counter()
        resp = send(proc, {"id": 1 + i, "kind": "prefill",
                           "prompt_tokens": prompt})
        b = time.perf_counter()
        spans.append((a, b))
        tokens.append(resp.get("token"))
        print(f"prefill {i}: {(b - a) * 1e3:8.2f} ms  "
              f"({(b - a) / len(prompt) * 1e6:6.2f} us/token)  "
              f"token={resp.get('token')}")
    if len(set(tokens)) != 1:
        print(f"WARNING: prefill greedy tokens differ across reps: {tokens}")

    decode_spans = []
    if args.decode_steps:
        send(proc, {"id": 500, "kind": "decode_begin", "seed_tokens": prompt})
        tok = tokens[-1]
        for i in range(args.decode_steps):
            a = time.perf_counter()
            resp = send(proc, {"id": 600 + i, "kind": "decode_step",
                               "token": tok})
            b = time.perf_counter()
            decode_spans.append((a, b))
            tok = resp["token"]
        med = sorted(b - a for a, b in decode_spans)[len(decode_spans) // 2]
        print(f"decode: {med * 1e3:.3f} ms/step median over "
              f"{len(decode_spans)} steps")

    diag = send(proc, {"id": 901, "kind": "phase_diagnostics"})
    print("peak_ram_gb:", diag.get("peak_ram_gb"))
    proc.stdin.close()
    proc.wait(timeout=60)
    err.flush()
    err.close()

    warm = spans[1:] if len(spans) > 1 else spans
    med = sorted(b - a for a, b in warm)[len(warm) // 2]
    print(f"\nprefill warm median: {med * 1e3:.3f} ms/forward "
          f"({med / len(prompt) * 1e6:.2f} us/token) over {len(warm)} reps")

    if args.profile:
        records = parse_gpuprof(args.stderr)
        analyze(records, warm, args.ceiling_gbs, args.profile_top,
                "prefill warm")
        if decode_spans:
            analyze(records, decode_spans[1:], args.ceiling_gbs,
                    args.profile_top, "decode steady")


if __name__ == "__main__":
    main()
