#!/usr/bin/env python3
"""Research-only decode boundary-gap probe (PR #241, not submitted).

Prices ONE producer->consumer chain link on the decode spine. At the named
site the runtime instrument (`LagunaDecodeGap`) inserts K chained bit-exact
identity multiplies *inside the real dependency chain* immediately in front of
the consumer, so MLX must emit K extra dispatches and K extra RAW barriers that
no sibling can shadow. Each copy moves ~8 KB, i.e. ~0.06 us of real bandwidth
work at 260 GB/s, so the marginal per-step cost of a copy is essentially the
serial dispatch + boundary price -- exactly what fusing the producer into the
consumer's prologue would delete.

Injecting *at the boundary* prices `E x g` directly: a boundary whose consumer
has absorbed slack self-reports ~0 without any separate elasticity weighting.
`T0a_router_top8` (E = -0.045 in the PR #218 ledger) is the built-in shadow
control; a non-zero slope there would mean the instrument is measuring
something other than serial boundary cost.

All arms live in ONE worker process (one 41 s model load, one allocator state,
one thermal state). Each schedule segment is a fresh `decode_begin` plus
`--steps-per-segment` teacher-forced one-token steps over identical token
content, and the schedule is palindromic so linear drift cancels inside a
block. Output is the PR #218 TSV format, so research/fern_dup_stats.py reduces
it unchanged.

  python3 research/fern_gap_probe.py --site T0b_qkv \
      --schedule 0,1,2,4,4,2,1,0 --blocks 3 --steps-per-segment 216 \
      --out /tmp/gap_t0b.tsv

Every model-holding run must be the only one on the host.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import time
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = os.path.join(REPO, ".build-worker/release/mlxfast-runtime-worker")
GOLDEN = os.path.join(
    REPO, "correctness_prompts/public_longcopy_gate_english_512_256.json"
)
SEG_RE = re.compile(r"^GAPSEG (\d+) site=(\S*) k=(\d+)")
COUNT_RE = re.compile(r"^GAPCOUNT seg=(\d+) step=(\d+) k=(\d+) site=(\S*) (.*)$")


def mach_now() -> float:
    """Seconds on the mach absolute-time epoch (see research/decode_probe.py)."""
    return time.clock_gettime(time.CLOCK_UPTIME_RAW)


def parse_gapseg(path: str) -> dict:
    out = {}
    with open(path, "rb") as fh:
        for raw in fh:
            m = SEG_RE.match(raw.decode("utf-8", "replace").strip())
            if m:
                out[int(m.group(1))] = int(m.group(3))
    return out


def report_census(path: str, site: str) -> bool:
    """REACHABILITY-BEFORE-NULL: observed call counts for every wired site."""
    buckets = defaultdict(lambda: defaultdict(int))
    lines = 0
    with open(path, "rb") as fh:
        for raw in fh:
            m = COUNT_RE.match(raw.decode("utf-8", "replace").strip())
            if not m:
                continue
            lines += 1
            for item in m.group(5).split(","):
                if "=" not in item:
                    continue
                name, n = item.split("=", 1)
                buckets[name][int(n)] += 1
    if not lines:
        print("census: NO GAPCOUNT lines -- no wired site was reached; every "
              "timing below is uninterpretable", flush=True)
        return False
    targets = [t.strip() for t in site.split(",") if t.strip()]
    print(f"census: {lines} instrumented decode steps", flush=True)
    for name in sorted(buckets):
        hist = dict(sorted(buckets[name].items()))
        mark = "  <== TARGET" if name in targets else ""
        print(f"census {name}: calls/step {hist}{mark}", flush=True)
    missing = [t for t in targets if t not in buckets]
    if missing:
        print(f"census: SITE(S) {','.join(missing)} NEVER REACHED -- the timing "
              "below cannot be read as a boundary price", flush=True)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True,
                    help="DARKBLOOM_DECODE_GAP_SITE chain-link name")
    ap.add_argument("--schedule", default="0,1,2,4,4,2,1,0",
                    help="palindromic per-segment K (chained copies) schedule")
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--steps-per-segment", type=int, default=216)
    ap.add_argument("--drop", type=int, default=16,
                    help="warmup steps dropped from each segment median")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stderr", default=None)
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--verbose-census", action="store_true", default=True)
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
    env["DARKBLOOM_DECODE_GAP_SITE"] = args.site
    env["DARKBLOOM_DECODE_GAP_SCHEDULE"] = ",".join(str(k) for k in schedule)
    env["DARKBLOOM_DECODE_GAP_VERBOSE"] = "1" if args.verbose_census else "0"

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
          f"site={args.site} schedule={schedule} x{args.blocks} "
          f"steps/seg={args.steps_per_segment}", flush=True)

    # Alignment: the model load itself issues a seed-length warmup forward,
    # which opens a segment the probe never drove. Burn throwaway segments
    # until the next worker segment index is a multiple of the schedule length.
    rid += 1
    send({"id": rid, "kind": "decode_begin", "seed_tokens": prompt})
    rid += 1
    send({"id": rid, "kind": "decode_step", "token": expected[0]})
    last = max(parse_gapseg(err_path), default=-1)
    if last < 0:
        raise SystemExit(
            "no GAPSEG line after an alignment segment: the instrument is not "
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

    observed = parse_gapseg(err_path)
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

    with open(args.out, "w") as fh:
        fh.write(f"# site={args.site} schedule={args.schedule} "
                 f"blocks={args.blocks} steps_per_segment="
                 f"{args.steps_per_segment} drop={args.drop} "
                 f"start={start} divergences={len(divergences)}\n")
        fh.write("segment\tk\tstep\tms\n")
        for seg, k, step, ms in rows:
            fh.write(f"{seg}\t{k}\t{step}\t{ms:.6f}\n")
    reached = report_census(err_path, args.site)
    print(f"wrote {len(rows)} timed steps -> {args.out}\n"
          f"worker stderr -> {err_path}", flush=True)
    if divergences:
        return 1
    return 0 if reached else 3


if __name__ == "__main__":
    raise SystemExit(main())
