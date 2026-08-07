#!/usr/bin/env python3
"""Research-only dispatch-tax attribution probe (PR #268, not submitted).

PR #241 priced one decode producer->consumer chain link at ~1.4 us/dispatch on
this M4 Pro host but did not say WHAT the 1.4 us buys. This driver runs the
`LagunaTaxProbe` instrument, which injects controlled dispatch work with a
known dependency structure, dirty footprint, and distinct-resource count, and
reads back the Metal backend's real dispatch / barrier / command-buffer
counters plus per-command-buffer GPU busy time.

Modes (DARKBLOOM_TAX_MODE):

  chain40   in-chain at the T0b_qkv consumer, K chained identity multiplies
            per layer (40 calls/step) -- the exact PR #241 wiring, replicated
            in this session so every other arm can be tied to its scale.
  spin40    same encode position, same 40 calls/step, but the GPU work is
            replaced by K * DARKBLOOM_TAX_SPIN_NS of pure CPU busy-spin. Prices
            E1 (CPU-side per-op encode starving the GPU) directly.
  chain     off-chain batch at end of step: K chained identity multiplies off a
            pre-materialized constant. K dispatches, K-1 RAW barriers.
  indep     off-chain batch: K independent multiplies off the SAME constant.
            K dispatches, ~0 barriers. chain-minus-indep isolates barrier cost
            (E3 flush) from raw launch cost (E2).
  distinct  off-chain batch: K independent multiplies off K DISTINCT constants.
            distinct-minus-indep isolates residency/bookkeeping cost (E4).
  diamond1  off-chain batch: K joins, each fed by one producer read twice.
  diamond2  off-chain batch: K joins, each fed by two independent producers.
            diamond2-minus-diamond1 prices one dispatch on a parallel arm (B2).

All arms of a schedule live in ONE worker process (one model load, one
allocator state, one thermal state). Each segment is a fresh `decode_begin`
plus --steps-per-segment teacher-forced one-token steps over identical token
content; the schedule is palindromic so linear drift cancels inside a block.

  python3 research/fern_tax_probe.py --mode chain \
      --schedule 0,32,64,128,128,64,32,0 --blocks 3 --out /tmp/tax_chain.tsv

Every model-holding run must be the only one on the host.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)
SEG_RE = re.compile(r"^TAXSEG (\d+) mode=(\S+) k=(\d+) bytes=(\d+)")
CTR_RE = re.compile(r"^TAXCTR (.*)$")


def mach_now() -> float:
    return time.clock_gettime(time.CLOCK_UPTIME_RAW)


def parse_segs(path: str) -> dict:
    out = {}
    with open(path, "rb") as fh:
        for raw in fh:
            m = SEG_RE.match(raw.decode("utf-8", "replace").strip())
            if m:
                out[int(m.group(1))] = int(m.group(3))
    return out


def parse_counters(path: str) -> list:
    """TAXCTR key=value records, one per instrumented decode step."""
    rows = []
    with open(path, "rb") as fh:
        for raw in fh:
            m = CTR_RE.match(raw.decode("utf-8", "replace").strip())
            if not m:
                continue
            rec = {}
            for item in m.group(1).split():
                if "=" not in item:
                    continue
                k, v = item.split("=", 1)
                rec[k] = int(v) if v.isdigit() else v
            rows.append(rec)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--schedule", default="0,32,64,128,128,64,32,0")
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--steps-per-segment", type=int, default=216)
    ap.add_argument("--drop", type=int, default=16)
    ap.add_argument("--bytes", type=int, default=8192)
    ap.add_argument("--pool", type=int, default=256)
    ap.add_argument("--anchor", type=int, default=1, choices=(0, 1))
    ap.add_argument("--spin-ns", type=int, default=1400)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stderr", default=None)
    ap.add_argument("--weights", default="weights")
    args = ap.parse_args()

    schedule = [int(x) for x in args.schedule.split(",") if x.strip()]
    if not schedule:
        raise SystemExit("empty --schedule")
    err_path = args.stderr or (args.out + ".worker.err")

    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt = case["prompt_tokens"]
    expected = case["expected_tokens"]
    if args.steps_per_segment > len(expected) - 1:
        raise SystemExit(
            f"--steps-per-segment {args.steps_per_segment} exceeds the "
            f"{len(expected)-1} teacher-forced steps the golden case supplies")

    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    env["DARKBLOOM_TAX_MODE"] = args.mode
    env["DARKBLOOM_TAX_SCHEDULE"] = ",".join(str(k) for k in schedule)
    env["DARKBLOOM_TAX_BYTES"] = str(args.bytes)
    env["DARKBLOOM_TAX_POOL"] = str(args.pool)
    env["DARKBLOOM_TAX_ANCHOR"] = str(args.anchor)
    env["DARKBLOOM_TAX_SPIN_NS"] = str(args.spin_ns)

    errfh = open(err_path, "wb")
    t_launch = time.perf_counter()
    proc = subprocess.Popen(
        [WORKER, "runtime-worker", "--weights", args.weights],
        cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=errfh, env=env, bufsize=1, text=True,
    )
    rid = 1000

    def send(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("worker closed stdout; see " + err_path)
        resp = json.loads(line)
        if not resp.get("ok", False):
            raise SystemExit("worker error: " + json.dumps(resp))
        return resp

    hello = json.loads(proc.stdout.readline())
    print(f"worker up in {time.perf_counter()-t_launch:.1f}s ok={hello.get('ok')} "
          f"mode={args.mode} bytes={args.bytes} spin_ns={args.spin_ns} "
          f"schedule={schedule} x{args.blocks} steps/seg={args.steps_per_segment}",
          flush=True)

    # The model load itself issues a seed-length warmup forward, which opens a
    # segment the probe never drove. Burn throwaway segments until the next
    # worker segment index is a multiple of the schedule length.
    rid += 1
    send({"id": rid, "kind": "decode_begin", "seed_tokens": prompt})
    rid += 1
    send({"id": rid, "kind": "decode_step", "token": expected[0]})
    last = max(parse_segs(err_path), default=-1)
    if last < 0:
        raise SystemExit(
            "no TAXSEG line after an alignment segment: the instrument is not "
            f"active; check worker stderr at {err_path}")
    burn = -(last + 1) % len(schedule)
    for _ in range(burn):
        rid += 1
        send({"id": rid, "kind": "decode_begin", "seed_tokens": prompt})
        rid += 1
        send({"id": rid, "kind": "decode_step", "token": expected[0]})
    start = last + 1 + burn
    print(f"alignment: worker was at segment {last}, burned {burn}, real "
          f"segments start at worker index {start}", flush=True)

    n_segments = len(schedule) * args.blocks
    rows, divergences = [], []
    t_start = time.perf_counter()
    for seg in range(n_segments):
        k_intended = schedule[seg % len(schedule)]
        rid += 1
        send({"id": rid, "kind": "decode_begin", "seed_tokens": prompt})
        token = expected[0]
        for step in range(args.steps_per_segment):
            rid += 1
            t0 = mach_now()
            resp = send({"id": rid, "kind": "decode_step", "token": token})
            rows.append((seg, k_intended, step, (mach_now() - t0) * 1e3))
            if resp["token"] != expected[step + 1]:
                divergences.append((seg, step, expected[step + 1], resp["token"]))
            token = expected[step + 1]
        med = statistics.median(
            r[3] for r in rows[-args.steps_per_segment + args.drop:])
        print(f"segment {seg:3d} k={k_intended} median={med:.4f} ms "
              f"elapsed={time.perf_counter()-t_start:.0f}s", flush=True)

    print(f"teacher-forced greedy tokens: {len(divergences)} divergences"
          + (f" first={divergences[0]}" if divergences else " (all match)"),
          flush=True)

    proc.stdin.close()
    proc.wait(timeout=120)
    errfh.close()

    observed = parse_segs(err_path)
    missing = [start + j for j in range(n_segments) if start + j not in observed]
    mismatch = [(start + j, observed[start + j], schedule[j % len(schedule)])
                for j in range(n_segments)
                if start + j in observed
                and observed[start + j] != schedule[j % len(schedule)]]
    if missing or mismatch:
        print(f"FATAL phase check: missing={missing[:8]} mismatch="
              f"{mismatch[:8]}", flush=True)
        return 2
    print(f"phase check ok: instrument announced the intended K for all "
          f"{n_segments} segments (worker {start}..{start+n_segments-1})",
          flush=True)

    # Counters are keyed by the worker's own segment index; realign to the
    # driver's segment numbering and drop the alignment/burn segments.
    ctrs = parse_counters(err_path)
    by_seg = {}
    for rec in ctrs:
        s = rec.get("seg", -1) - start
        if 0 <= s < n_segments and rec.get("step", 0) >= args.drop:
            by_seg.setdefault(s, []).append(rec)

    with open(args.out, "w") as fh:
        fh.write(f"# mode={args.mode} schedule={args.schedule} "
                 f"blocks={args.blocks} steps_per_segment="
                 f"{args.steps_per_segment} drop={args.drop} "
                 f"bytes={args.bytes} pool={args.pool} anchor={args.anchor} "
                 f"spin_ns={args.spin_ns} "
                 f"start={start} divergences={len(divergences)}\n")
        fh.write("segment\tk\tstep\tms\n")
        for seg, k, step, ms in rows:
            fh.write(f"{seg}\t{k}\t{step}\t{ms:.6f}\n")

    cpath = args.out + ".ctr.tsv"
    keys = ["dispatch", "barrier", "commit", "gpu_ns", "kernel_ns", "span_ns",
            "encode", "sitecalls"]
    with open(cpath, "w") as fh:
        fh.write("segment\tk\tn\t" + "\t".join(keys) + "\n")
        for seg in sorted(by_seg):
            recs = by_seg[seg]
            k = recs[0].get("k", 0)
            meds = [statistics.median(r.get(key, 0) for r in recs) for key in keys]
            fh.write(f"{seg}\t{k}\t{len(recs)}\t"
                     + "\t".join(f"{m:.1f}" for m in meds) + "\n")

    if not by_seg:
        print("counters: NO TAXCTR rows -- the backend probe never fired; "
              "every attribution below is uninterpretable", flush=True)
        return 3
    print(f"counters: {sum(len(v) for v in by_seg.values())} instrumented "
          f"steps across {len(by_seg)} segments -> {cpath}", flush=True)
    for seg in sorted(by_seg):
        recs = by_seg[seg]
        k = recs[0].get("k", 0)
        d = statistics.median(r.get("dispatch", 0) for r in recs)
        b = statistics.median(r.get("barrier", 0) for r in recs)
        c = statistics.median(r.get("commit", 0) for r in recs)
        g = statistics.median(r.get("gpu_ns", 0) for r in recs) / 1e6
        sp = statistics.median(r.get("span_ns", 0) for r in recs) / 1e6
        sc = statistics.median(r.get("sitecalls", 0) for r in recs)
        print(f"ctr seg {seg:3d} k={k:4d} dispatch={d:7.0f} barrier={b:7.0f} "
              f"commit={c:5.0f} gpu={g:.3f}ms span={sp:.3f}ms sites={sc:.0f}",
              flush=True)

    print(f"wrote {len(rows)} timed steps -> {args.out}\n"
          f"worker stderr -> {err_path}", flush=True)
    return 1 if divergences else 0


if __name__ == "__main__":
    raise SystemExit(main())
