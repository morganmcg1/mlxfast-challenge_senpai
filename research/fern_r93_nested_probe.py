#!/usr/bin/env python3
"""R93-B nested-design decode probe (research only, not part of the submission).

One invocation is ONE process level of the nested design

    process p  >  run r (a fresh `decode_begin`)  >  step s

so `sigma_process`, `sigma_run|process` and `sigma_step|run` can be separated.
Prior campaign rigs spent one process per slot, which confounds the first two.
`decode_begin` rebuilds the KV cache and resets the allocator, so repeating it
inside one worker is a genuine independent run of the decode phase.

The ladder arm is written into a shared control word (`--glue-map`) that the
model reads once per decode forward, so the K rung can change between steps of
one run. That makes a ladder contrast step-paired instead of process-paired.

  python3 research/fern_r93_nested_probe.py --runs 4 --steps 120 \
      --out /tmp/r93/p0.json --process-index 0

Every model-holding run must be the only one on the host.

The supervised-job PATH resolves `python3` to the macOS system 3.9, so keep this
file free of runtime-evaluated 3.10+ syntax.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
import random
import struct
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.environ.get("DECODE_PROBE_WORKER") or os.path.join(
    REPO, ".build-worker/release/mlxfast-runtime-worker"
)
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)
MACMON = os.path.expanduser("~/bin/macmon")


def mach_now() -> float:
    """Seconds on the same epoch as `MTLCommandBuffer.GPUStartTime`."""
    return time.clock_gettime(time.CLOCK_UPTIME_RAW)


class Thermals:
    """Background `macmon pipe` sampler; latest sample is read lock-free."""

    def __init__(self, interval_ms: int = 500):
        self.latest = {}
        self.proc = None
        if not os.path.exists(MACMON):
            return
        self.proc = subprocess.Popen(
            [MACMON, "pipe", "-s", str(max(1, interval_ms // 1000))],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            try:
                s = json.loads(line)
            except ValueError:
                continue
            self.latest = {
                "gpu_c": s.get("temp", {}).get("gpu_temp_avg"),
                "cpu_c": s.get("temp", {}).get("cpu_temp_avg"),
                "gpu_w": s.get("gpu_power"),
                "all_w": s.get("all_power"),
            }

    def sample(self):
        return dict(self.latest)

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()


def open_glue_map(path: str):
    """Map (creating if needed) the 4-byte arm control word shared with the model."""
    if not path:
        return None
    if not os.path.exists(path) or os.path.getsize(path) < 4:
        with open(path, "wb") as fh:
            fh.write(b"\0\0\0\0")
    fh = open(path, "r+b")
    mm = mmap.mmap(fh.fileno(), 4)
    return mm


def parse_schedule(spec: str, steps: int, run_index: int = 0,
                   rng: random.Random | None = None, placebo_every: int = 0):
    """Expand an arm schedule into one (depth, slot, block, placebo) per step.

    `slot` is the rung a step was *assigned* to; on a placebo block every step
    runs at the reference depth but keeps its intended slot, so the identical
    contrast can be formed on data whose true delta is exactly zero.

    `const:N`            every step at depth N
    `perrun:A,B,...`     one constant depth for the whole run, cycling over the
                         listed depths by run index: a switching-free control
                         for any per-step ordering artefact
    `abba:A,B[,period]`  counterbalanced A/B in ABBA blocks of `period` steps
                         each (default 1), which cancels a linear within-run
                         drift over each duplex.
    `ladder:a,b,c,...`   round-robin over the listed depths, one step each
    `mirror:a,b,c,...`   the same depths forward then reversed, so every depth
                         has the same mean position inside the block and a
                         linear within-run drift cancels exactly for all arms
    `rand:a,b,c,...`     each depth twice per block of 2*len(depths) steps,
                         freshly permuted per block from `rng`. Unlike `mirror`
                         this leaves the own-depth/previous-depth correlation
                         near zero, so a carryover term is identifiable, and it
                         breaks the fixed token-position/rung pairing that no
                         amount of extra data would average away.
    """
    kind, _, rest = spec.partition(":")

    def plain(depths):
        return [(d, None, i // max(len(depths), 1), False)
                for i, d in enumerate(depths)]

    if kind == "const":
        return plain([int(rest)] * steps)
    if kind == "perrun":
        depths = [int(x) for x in rest.split(",")]
        d = depths[run_index % len(depths)]
        return plain([d] * steps)
    if kind == "abba":
        parts = [int(x) for x in rest.split(",")]
        a, b = parts[0], parts[1]
        period = parts[2] if len(parts) > 2 else 1
        pattern = [a] * period + [b] * period + [b] * period + [a] * period
        return plain([pattern[i % len(pattern)] for i in range(steps)])
    if kind == "ladder":
        depths = [int(x) for x in rest.split(",")]
        return plain([depths[i % len(depths)] for i in range(steps)])
    if kind == "mirror":
        depths = [int(x) for x in rest.split(",")]
        pattern = depths + depths[::-1]
        out = []
        for i in range(steps):
            out.append((pattern[i % len(pattern)], i % len(pattern) if
                        i % len(pattern) < len(depths)
                        else len(pattern) - 1 - i % len(pattern),
                        i // len(pattern), False))
        return out
    if kind == "rand":
        if rng is None:
            raise SystemExit("rand schedule needs a seeded rng")
        depths = [int(x) for x in rest.split(",")]
        block_len = 2 * len(depths)
        out = []
        # Which block inside each placebo window is the null is itself drawn,
        # so a placebo never samples one fixed phase of a block-periodic cycle.
        offset = rng.randrange(placebo_every) if placebo_every > 0 else -1
        while len(out) < steps:
            block = len(out) // block_len
            slots = [s for s in range(len(depths)) for _ in range(2)]
            rng.shuffle(slots)
            placebo = placebo_every > 0 and block % placebo_every == offset
            for s in slots:
                out.append((depths[0] if placebo else depths[s], s,
                            block, placebo))
        return out[:steps]
    raise SystemExit(f"unknown schedule {spec!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=4,
                    help="`decode_begin` calls inside this one worker process")
    ap.add_argument("--steps", type=int, default=120, help="decode steps per run")
    ap.add_argument("--out", required=True, help="JSON result path")
    ap.add_argument("--process-index", type=int, default=0)
    ap.add_argument("--label", default="")
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--stderr", default="/tmp/fern_r93_worker.err")
    ap.add_argument("--glue-map", default="",
                    help="path of the 4-byte shared arm control word; also "
                         "exported to the worker as DARKBLOOM_R93_GLUE_MAP")
    ap.add_argument("--schedule", default="const:0",
                    help="per-step arm schedule, see parse_schedule")
    ap.add_argument("--warmup-runs", type=int, default=1,
                    help="leading runs recorded but flagged as warmup")
    ap.add_argument("--no-thermals", action="store_true")
    ap.add_argument("--seed", type=int, default=93,
                    help="base seed for randomised schedules; the per-run "
                         "seed is recorded so any block order is replayable")
    ap.add_argument("--placebo-every", type=int, default=0,
                    help="every Nth block runs entirely at the reference "
                         "depth while keeping its assigned slots, giving an "
                         "in-session null whose true delta is exactly 0")
    args = ap.parse_args()

    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt = case["prompt_tokens"]
    expected = case["expected_tokens"]
    if args.steps + 1 > len(expected):
        raise SystemExit(
            f"--steps {args.steps} exceeds the golden's {len(expected)-1} "
            "teacher-forced steps; a longer run would leave the checked stream")

    # One stream per (seed, process) so every run gets a different permutation
    # while the whole session stays reproducible from the logged seed.
    run_seed = args.seed + 1_000_003 * args.process_index
    glue = open_glue_map(args.glue_map)
    if glue is not None:
        glue[:4] = struct.pack("<i", 0)

    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    if args.glue_map:
        env["DARKBLOOM_R93_GLUE_MAP"] = os.path.abspath(args.glue_map)
    errfh = open(args.stderr, "wb")
    t_launch = time.perf_counter()
    proc = subprocess.Popen(
        [WORKER, "runtime-worker", "--weights", args.weights],
        cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errfh,
        env=env, bufsize=1, text=True,
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

    hello_line = proc.stdout.readline()
    if not hello_line.strip():
        proc.kill()
        raise SystemExit(
            f"worker {args.worker} never wrote its hello line "
            f"(exit={proc.poll()}); check {args.stderr}. A staged binary needs "
            "mlx.metallib and the resource bundles in its own directory.")
    hello = json.loads(hello_line)
    load_seconds = time.perf_counter() - t_launch
    print(f"worker up in {load_seconds:.1f}s ok={hello.get('ok')}", flush=True)

    therm = None if args.no_thermals else Thermals()
    records = []
    runs_meta = []
    req_id = 1000
    stream_hashes = set()
    mismatch_total = 0

    for r in range(args.runs):
        if glue is not None:
            glue[:4] = struct.pack("<i", 0)
        seed_r = run_seed + 7919 * r
        schedule = parse_schedule(args.schedule, args.steps, r,
                                  random.Random(seed_r), args.placebo_every)
        t0 = mach_now()
        req_id += 1
        send({"id": req_id, "kind": "decode_begin", "seed_tokens": prompt})
        seed_ms = (mach_now() - t0) * 1e3

        generated = []
        token = expected[0]
        for s in range(args.steps):
            depth, slot, block, placebo = schedule[s]
            if glue is not None:
                glue[:4] = struct.pack("<i", depth)
            elif depth:
                raise SystemExit("schedule requests glue but --glue-map is unset")
            t_start = mach_now()
            req_id += 1
            resp = send({"id": req_id, "kind": "decode_step", "token": token})
            t_end = mach_now()
            generated.append(resp["token"])
            if resp["token"] != expected[s + 1]:
                mismatch_total += 1
            token = expected[s + 1]
            rec = {
                "process": args.process_index,
                "run": r,
                "step": s,
                "glue": depth,
                "k": depth * 40,
                "us": (t_end - t_start) * 1e6,
                "t": t_start,
                "warmup_run": r < args.warmup_runs,
            }
            if slot is not None:
                rec["slot"] = slot
                rec["block"] = block
                rec["placebo"] = placebo
            if therm is not None and (s % 8 == 0):
                rec.update(therm.sample())
            records.append(rec)

        digest = hashlib.sha256(
            ",".join(str(t) for t in generated).encode()).hexdigest()[:16]
        stream_hashes.add(digest)
        runs_meta.append({"run": r, "seed_ms": seed_ms, "token_hash": digest,
                          "schedule_seed": seed_r})
        print(f"run {r}: seed={seed_ms:.1f}ms hash={digest} "
              f"median_us={sorted(x['us'] for x in records[-args.steps:])[args.steps//2]:.1f}",
              flush=True)

    if glue is not None:
        glue[:4] = struct.pack("<i", 0)
        glue.close()
    if therm is not None:
        therm.stop()
    proc.stdin.close()
    proc.wait(timeout=120)
    errfh.close()

    out = {
        "process": args.process_index,
        "label": args.label,
        "schedule": args.schedule,
        "seed": args.seed,
        "placebo_every": args.placebo_every,
        "runs": args.runs,
        "steps": args.steps,
        "warmup_runs": args.warmup_runs,
        "load_seconds": load_seconds,
        "token_stream_hashes": sorted(stream_hashes),
        "teacher_forced_mismatches": mismatch_total,
        "runs_meta": runs_meta,
        "records": records,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh)
    print(f"hashes={sorted(stream_hashes)} mismatches={mismatch_total} -> {args.out}",
          flush=True)
    if len(stream_hashes) != 1:
        print("FAIL: token stream differs across runs (rule 45 bit-exactness)",
              file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
