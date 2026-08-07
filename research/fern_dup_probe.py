#!/usr/bin/env python3
"""Research-only segmented duplicate-injection probe (PR #218, not submitted).

Prices one named decode dispatch family by re-issuing it `K-1` extra times per
call and regressing steady per-step time on `K`. All arms live in ONE worker
process so a single 41 s model load, one allocator state and one thermal state
are shared: `decode_begin` is re-issuable, so each schedule *segment* is a
fresh cache plus `--steps-per-segment` teacher-forced one-token steps over the
identical token content and the identical KV range. The instrument advances its
own arm on every seed prefill, so the segment schedule
(`1,2,3,5,5,3,2,1` x blocks) is palindromic in time and cancels linear drift
inside each block.

  python3 research/fern_dup_probe.py --target T0a_router_top8 \
      --schedule 1,2,3,5,5,3,2,1 --blocks 3 --steps-per-segment 216 \
      --out /tmp/t0a.tsv

Every model-holding run must be the only one on the host.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)


def mach_now() -> float:
    """Seconds on the mach absolute-time epoch (see research/decode_probe.py)."""
    return time.clock_gettime(time.CLOCK_UPTIME_RAW)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True,
                    help="DARKBLOOM_DECODE_DUP_TARGET dispatch family name")
    ap.add_argument("--schedule", default="1,2,3,5,5,3,2,1",
                    help="per-segment copy counts, applied cyclically")
    ap.add_argument("--blocks", type=int, default=3,
                    help="how many times to repeat the schedule")
    ap.add_argument("--steps-per-segment", type=int, default=216)
    ap.add_argument("--drop", type=int, default=16,
                    help="leading steps discarded from every segment")
    ap.add_argument("--out", required=True, help="per-step TSV output path")
    ap.add_argument("--stderr", default=None)
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--fault", action="store_true",
                    help="perturb the REAL dispatch input by 1 bf16 ULP")
    ap.add_argument("--verbose-census", action="store_true",
                    help="worker prints its per-step injected-call census")
    ap.add_argument("--chain", action="store_true")
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
            f"{len(expected)-1} teacher-forced steps the golden case supplies; "
            "every segment must be identical work")

    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    env["DARKBLOOM_DECODE_DUP_TARGET"] = args.target
    env["DARKBLOOM_DECODE_DUP_SCHEDULE"] = ",".join(str(k) for k in schedule)
    env["DARKBLOOM_DECODE_DUP_FAULT"] = "1" if args.fault else "0"
    env["DARKBLOOM_DECODE_DUP_VERBOSE"] = "1" if args.verbose_census else "0"
    env["DARKBLOOM_DECODE_DUP_CHAIN"] = "1" if args.chain else "0"

    errfh = open(err_path, "wb")
    t_launch = time.perf_counter()
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
            raise SystemExit("worker closed stdout; see " + err_path)
        resp = json.loads(line)
        if not resp.get("ok", False):
            raise SystemExit("worker error: " + json.dumps(resp))
        return resp

    hello = json.loads(proc.stdout.readline())
    print(f"worker up in {time.perf_counter()-t_launch:.1f}s "
          f"ok={hello.get('ok')} target={args.target} "
          f"schedule={schedule} x{args.blocks} "
          f"steps/seg={args.steps_per_segment} fault={int(args.fault)}",
          flush=True)

    n_segments = len(schedule) * args.blocks
    rows = []
    divergences = []
    rid = 1000

    # Alignment. Model load itself issues a seed-length warmup forward, which
    # opens a schedule segment the probe never drove; left uncorrected that
    # rotates every arm by one and silently mislabels the whole run. Burn
    # throwaway segments until the worker's next segment index is a multiple of
    # the schedule length, so real segment j really does get schedule[j].
    rid += 1
    send({"id": rid, "kind": "decode_begin", "seed_tokens": prompt})
    rid += 1
    send({"id": rid, "kind": "decode_step", "token": expected[0]})
    last = max(parse_dupseg(err_path), default=-1)
    if last < 0:
        raise SystemExit(
            "no DUPSEG line after an alignment segment: the instrument is not "
            f"active (target={args.target!r} unknown, or worker stderr is not "
            f"{err_path})")
    burn = -(last + 1) % len(schedule)
    for _ in range(burn):
        rid += 1
        send({"id": rid, "kind": "decode_begin", "seed_tokens": prompt})
        rid += 1
        send({"id": rid, "kind": "decode_step", "token": expected[0]})
    start = last + 1 + burn
    print(f"alignment: worker was at segment {last}, burned {burn} throwaway "
          f"segments, real segments start at worker index {start}", flush=True)

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

    observed = parse_dupseg(err_path)
    missing = [start + j for j in range(n_segments)
               if start + j not in observed]
    mismatch = [(start + j, observed[start + j], schedule[j % len(schedule)])
                for j in range(n_segments)
                if start + j in observed
                and observed[start + j] != schedule[j % len(schedule)]]
    if missing or mismatch:
        print(f"FATAL phase check: missing worker segments={missing[:8]} "
              f"arm mismatches (worker_seg, announced, intended)="
              f"{mismatch[:8]}", flush=True)
        return 2
    print(f"phase check ok: the instrument announced the intended K for all "
          f"{n_segments} real segments (worker indices {start}.."
          f"{start+n_segments-1})", flush=True)

    with open(args.out, "w") as fh:
        fh.write(f"# target={args.target} schedule={args.schedule} "
                 f"blocks={args.blocks} steps_per_segment="
                 f"{args.steps_per_segment} drop={args.drop} "
                 f"fault={int(args.fault)} verbose={int(args.verbose_census)} "
                 f"start={start} divergences={len(divergences)}\n")
        fh.write("segment\tk\tstep\tms\n")
        for seg, k, step, ms in rows:
            fh.write(f"{seg}\t{k}\t{step}\t{ms:.6f}\n")
    if args.verbose_census:
        report_census(err_path, args.target)
    print(f"wrote {len(rows)} timed steps -> {args.out}\n"
          f"worker stderr -> {err_path}", flush=True)
    return 1 if divergences else 0


def report_census(err_path: str, target: str) -> None:
    """Per-K histogram of injected calls per forward.

    The dominant bucket is `n_calls_per_step`; the rare small bucket is the
    seed prefill, which is outside every timed window.
    """
    hist = defaultdict(lambda: defaultdict(int))
    with open(err_path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("DUPCOUNT "):
                continue
            parts = line.split()
            k = int(parts[1].split("=", 1)[1])
            for field in parts[2].split(","):
                name, count = field.split("=")
                if name == target:
                    hist[k][int(count)] += 1
    for k in sorted(hist):
        buckets = ", ".join(f"{c} calls x{n}" for c, n in
                            sorted(hist[k].items(), key=lambda kv: -kv[1]))
        print(f"census K={k}: {buckets}", flush=True)


def parse_dupseg(err_path: str) -> dict:
    """segment index -> K, as announced by the instrument itself."""
    observed = {}
    with open(err_path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("DUPSEG "):
                continue
            parts = line.split()
            observed[int(parts[1])] = int(parts[3].split("=", 1)[1])
    return observed


if __name__ == "__main__":
    sys.exit(main())
