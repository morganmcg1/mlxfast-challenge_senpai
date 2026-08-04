#!/usr/bin/env python3
"""Research-only driver + per-dispatch analyzer for the 512-token prefill forward.

Companion to research/decode_probe.py, which only ever profiles steady decode
steps (it drops the seed forward and step 0 from its window). This script
profiles the scored `prefill` request instead: one 512-token forward per request
against a fresh cache, which is the shape of the scored prefill axis and of the
seed forward charged into the decode figure.

Requires the LOCAL-ONLY GPUPROF hooks in the vendored MLX
backend/metal/device.cpp|.h (env DARKBLOOM_GPU_PROFILE=1, optionally
DARKBLOOM_GPU_PROFILE_SPLIT=1 for one command buffer per primitive). Those hooks
are reverted before any timing run.

Attribution is by request, not by timestamp: each worker request is synchronous,
so the profiler lines flushed to the worker's stderr between sending a request
and reading its response belong to that request. Per-request dispatch counts are
printed so an attribution or buffering error is visible rather than silent.

Usage:
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/prefill_probe.py --reps 6 --profile --profile-top 40
"""

import argparse
import json
import pathlib
import re
import subprocess
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKER = REPO / ".build-worker/release/mlxfast-runtime-worker"
GOLDEN = REPO / "correctness_prompts/public_longcopy_gate_english_512_256.json"


def load_prompt():
    case = json.loads(GOLDEN.read_text())["cases"][0]
    return case["prompt_tokens"]


def parse_gpuprof(text):
    """Return list of (gpu_start, gpu_end, nops, bytes, [names])."""
    records = []
    for line in text.splitlines():
        if not line.startswith("GPUPROF "):
            continue
        parts = line.split(" ", 5)
        if len(parts) < 6:
            continue
        try:
            start, end = float(parts[1]), float(parts[2])
            nops, nbytes = int(parts[3]), int(parts[4])
        except ValueError:
            continue
        names = parts[5].strip().split("|") if parts[5].strip() else []
        records.append((start, end, nops, nbytes, names))
    return records


class Worker:
    def __init__(self, weights, err_path):
        self.err_write = open(err_path, "w")
        self.proc = subprocess.Popen(
            [str(WORKER), "runtime-worker", "--weights", weights],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.err_write, text=True)
        self.err_read = open(err_path, "r", errors="replace")

    def drain(self):
        return self.err_read.read()

    def request(self, obj):
        """Send one request; return (response, elapsed, its GPUPROF records)."""
        self.drain()
        start = time.perf_counter()
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        elapsed = time.perf_counter() - start
        if not line:
            raise SystemExit("worker closed stdout")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise SystemExit(f"worker error: {resp}")
        return resp, elapsed, parse_gpuprof(self.drain())

    def hello(self):
        resp = json.loads(self.proc.stdout.readline())
        if not resp.get("ok"):
            raise SystemExit(f"worker hello failed: {resp}")
        return resp

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=120)
        self.err_write.flush()
        self.drain()
        self.err_write.close()
        self.err_read.close()


def shorten(name):
    name = re.sub(r"^custom_kernel_laguna_", "laguna_", name)
    name = re.sub(r"_(float16|bfloat16|float32)_t?(_.*)?$", "", name)
    return name[:76]


FAMILIES = (
    ("routed_gather_gemm", r"gather_qmm|gather_mm"),
    ("nvfp4_dense_qmm", r"nvfp4_qmm|qmm_splitk|nvfp4_qvm|quantized_matmul|qmv"),
    ("steel_gemm_bf16", r"steel_gemm|^gemm_|steel_matmul"),
    ("attention_core", r"attention|sdpa|steel_attn"),
    ("qk_norm_rope", r"qk_norm|rope|yarn"),
    ("router", r"router|topk|top8|tournament"),
    ("moe_tail", r"moe_tail"),
    ("sort_scatter", r"sort|scatter|gather_front|gather_axis|arange|partition|"
                     r"cumsum|take|index"),
    ("rms_norm", r"rms"),
    ("lm_head", r"lmhead|lm_head|argmax|argreduce|arg_reduce"),
    ("elementwise", r"binary|unary|copy|reduce|softmax|concat|slice|pad|fill|"
                    r"broadcast|astype|multiply|add|subtract|divide|silu|"
                    r"softplus|power|maximum|minimum|^v_|^vs_|^sv_|^vv_"),
)


def family(short):
    low = short.lower()
    for label, pattern in FAMILIES:
        if re.search(pattern, low):
            return label
    return "other"


def analyze(label, batches, ceiling_gbs, top_n):
    """batches: list of (elapsed_seconds, records) for identical requests."""
    if not batches:
        return
    n = len(batches)
    wall = sum(b[0] for b in batches)
    records = [r for _, recs in batches for r in recs]
    if not records:
        print(f"\nprofile [{label}]: no GPUPROF records "
              f"(was DARKBLOOM_GPU_PROFILE=1 set?)")
        return

    busy_sum = sum(e - s for s, e, _, _, _ in records)
    merged = []
    for s, e, _, _, _ in sorted(records):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    busy_union = sum(e - s for s, e in merged)
    dispatches = sum(r[2] for r in records)
    total_bytes = sum(r[3] for r in records)

    print(f"\nprofile [{label}] over {n} request(s)")
    print(f"  per-request dispatches "
          f"{[sum(r[2] for r in recs) for _, recs in batches]}")
    print(f"  wall             {wall / n * 1e3:9.3f} ms/request")
    print(f"  gpu busy (sum)   {busy_sum / n * 1e3:9.3f} ms "
          f"({busy_sum / wall * 100:5.1f}% of wall)")
    print(f"  gpu busy (union) {busy_union / n * 1e3:9.3f} ms "
          f"({busy_union / wall * 100:5.1f}% of wall)")
    print(f"  command buffers  {len(records) / n:9.1f} /request")
    print(f"  dispatches       {dispatches / n:9.1f} /request")
    print(f"  bound bytes      {total_bytes / n / 2**30:9.3f} GiB/request")

    agg = {}
    for s, e, nops, nbytes, names in records:
        if not names:
            key = "empty_commit"
        elif len(names) == 1:
            key = shorten(names[0])
        else:
            key = "MIXED:" + "+".join(sorted({shorten(x) for x in names}))[:68]
        slot = agg.setdefault(key, [0, 0.0, 0])
        slot[0] += max(1, len(names))
        slot[1] += e - s
        slot[2] += nbytes

    rows = sorted(agg.items(), key=lambda kv: -kv[1][1])
    print(f"\n  {'dispatch':<58} {'n/req':>6} {'us/call':>8} {'ms/req':>8} "
          f"{'%wall':>6} {'MB/call':>8} {'GB/s':>7} {'%bw':>5} {'family':>18}")
    for name, (count, seconds, nbytes) in rows[:top_n]:
        per = seconds / n
        gbs = (nbytes / seconds) / 1e9 if seconds > 0 else 0.0
        print(f"  {name:<58} {count / n:6.1f} {seconds / count * 1e6:8.1f} "
              f"{per * 1e3:8.3f} {per / (wall / n) * 100:6.1f} "
              f"{nbytes / count / 2**20:8.3f} {gbs:7.1f} "
              f"{gbs / ceiling_gbs * 100:5.0f} {family(name):>18}")
    if len(rows) > top_n:
        tail = sum(v[1] for _, v in rows[top_n:]) / n
        print(f"  {f'... {len(rows) - top_n} more dispatch kinds':<58} "
              f"{'':>6} {'':>8} {tail * 1e3:8.3f} "
              f"{tail / (wall / n) * 100:6.1f}")

    fam = {}
    for name, (count, seconds, nbytes) in rows:
        slot = fam.setdefault(family(name), [0, 0.0, 0])
        slot[0] += count
        slot[1] += seconds
        slot[2] += nbytes
    print(f"\n  {'family':<20} {'n/req':>7} {'ms/req':>8} {'%wall':>6} "
          f"{'GB/s':>7} {'%bw':>5}")
    for label_, (count, seconds, nbytes) in sorted(
            fam.items(), key=lambda kv: -kv[1][1]):
        per = seconds / n
        gbs = (nbytes / seconds) / 1e9 if seconds > 0 else 0.0
        print(f"  {label_:<20} {count / n:7.1f} {per * 1e3:8.3f} "
              f"{per / (wall / n) * 100:6.1f} {gbs:7.1f} "
              f"{gbs / ceiling_gbs * 100:5.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=6,
                    help="prefill requests to issue (first is discarded)")
    ap.add_argument("--decode-steps", type=int, default=0)
    ap.add_argument("--weights", default=str(REPO / "weights"))
    ap.add_argument("--stderr", default="/tmp/prefill_probe.worker.err")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--profile-top", type=int, default=40)
    ap.add_argument("--ceiling-gbs", type=float, default=260.2)
    args = ap.parse_args()

    prompt = load_prompt()
    print(f"prompt tokens: {len(prompt)}")
    worker = Worker(args.weights, args.stderr)
    t0 = time.perf_counter()
    worker.hello()
    print(f"load: {time.perf_counter() - t0:.1f} s")
    worker.request({"id": 900, "kind": "phase_diagnostics"})

    prefills = []
    tokens = []
    for i in range(args.reps):
        resp, elapsed, records = worker.request(
            {"id": 1 + i, "kind": "prefill", "prompt_tokens": prompt})
        prefills.append((elapsed, records))
        tokens.append(resp.get("token"))
        print(f"prefill {i}: {elapsed * 1e3:8.2f} ms  "
              f"({elapsed / len(prompt) * 1e6:7.2f} us/token)  "
              f"cbs={len(records):5d} dispatches="
              f"{sum(r[2] for r in records):5d}  token={resp.get('token')}")
    if len(set(tokens)) != 1:
        print(f"WARNING: prefill greedy tokens differ across reps: {tokens}")

    decodes = []
    if args.decode_steps:
        resp, _, _ = worker.request(
            {"id": 500, "kind": "decode_begin", "seed_tokens": prompt})
        tok = resp.get("token", resp.get("seed_token"))
        for i in range(args.decode_steps):
            resp, elapsed, records = worker.request(
                {"id": 600 + i, "kind": "decode_step", "token": tok})
            decodes.append((elapsed, records))
            tok = resp["token"]
        med = sorted(e for e, _ in decodes)[len(decodes) // 2]
        print(f"decode: {med * 1e3:.3f} ms/step median over {len(decodes)}")

    diag, _, _ = worker.request({"id": 901, "kind": "phase_diagnostics"})
    print("peak_ram_gb:", diag.get("peak_ram_gb"))
    worker.close()

    warm = prefills[1:] if len(prefills) > 1 else prefills
    med = sorted(e for e, _ in warm)[len(warm) // 2]
    print(f"\nprefill warm median: {med * 1e3:.3f} ms/forward "
          f"({med / len(prompt) * 1e6:.2f} us/token) over {len(warm)} reps")

    if args.profile:
        analyze("prefill warm", warm, args.ceiling_gbs, args.profile_top)
        if len(decodes) > 1:
            analyze("decode steady", decodes[1:], args.ceiling_gbs,
                    args.profile_top)


if __name__ == "__main__":
    main()
