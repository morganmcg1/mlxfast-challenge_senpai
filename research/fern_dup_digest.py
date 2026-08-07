#!/usr/bin/env python3
"""Research-only logit-digest gate for research/fern_dup_probe.py (PR #218).

Untimed companion to the timed probe. Runs the same schedule on the worker's
teacher-forced `correctness_begin`/`correctness_step` path, which returns the
top-k logits, and hashes them per segment. Two claims have to hold before any
timing from a target is publishable:

  invariance   digest(K>1) == digest(K=1); the duplicates are pure scratch.
  sensitivity  digest(fault=1, K=1) != digest(fault=0, K=1); the digest can
               actually see a 1-ULP change at this exact site, so invariance
               is a result and not a tautology.

  python3 research/fern_dup_digest.py --target T0b_qkv --schedule 1,2,3,5
  python3 research/fern_dup_digest.py --target T0b_qkv --schedule 1 --fault

Every model-holding run must be the only one on the host.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

from fern_dup_probe import GOLDEN, REPO, WORKER, parse_dupseg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--schedule", default="1,2,3,5")
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--top-k", type=int, default=1024)
    ap.add_argument("--fault", action="store_true")
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--stderr", default="/tmp/fern_digest.worker.err")
    args = ap.parse_args()

    schedule = [int(x) for x in args.schedule.split(",") if x.strip()]
    with open(GOLDEN) as fh:
        case = json.load(fh)["cases"][0]
    prompt, expected = case["prompt_tokens"], case["expected_tokens"]

    env = dict(os.environ)
    env.setdefault("MLXFAST_WEIGHTS_PATH", args.weights)
    env["DARKBLOOM_DECODE_DUP_TARGET"] = args.target
    env["DARKBLOOM_DECODE_DUP_SCHEDULE"] = ",".join(str(k) for k in schedule)
    env["DARKBLOOM_DECODE_DUP_FAULT"] = "1" if args.fault else "0"
    env["DARKBLOOM_DECODE_DUP_VERBOSE"] = "0"
    env["DARKBLOOM_DECODE_DUP_CHAIN"] = "0"

    errfh = open(args.stderr, "wb")
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
            raise SystemExit("worker closed stdout; see " + args.stderr)
        resp = json.loads(line)
        if not resp.get("ok", False):
            raise SystemExit("worker error: " + json.dumps(resp))
        return resp

    json.loads(proc.stdout.readline())
    rid = 2000

    def segment(record: bool):
        nonlocal rid
        h = hashlib.sha256()
        rid += 1
        resp = send({"id": rid, "kind": "correctness_begin",
                     "prompt_tokens": prompt, "top_k": args.top_k,
                     "expected_token": expected[0]})
        for step in range(args.steps):
            rid += 1
            resp = send({"id": rid, "kind": "correctness_step",
                         "token": expected[step], "top_k": args.top_k,
                         "expected_token": expected[step + 1]})
            if record:
                for entry in resp["top_logits"]:
                    h.update(f"{entry['token']}:{entry['logit']!r}|".encode())
        return h.hexdigest()[:32]

    segment(record=False)
    last = max(parse_dupseg(args.stderr), default=-1)
    if last < 0:
        raise SystemExit(f"no DUPSEG line: instrument inactive for "
                         f"{args.target!r}")
    for _ in range(-(last + 1) % len(schedule)):
        segment(record=False)

    digests = {}
    for k in schedule:
        digests[k] = segment(record=True)
        print(f"K={k} digest={digests[k]}", flush=True)

    proc.stdin.close()
    proc.wait(timeout=120)
    errfh.close()

    observed = parse_dupseg(args.stderr)
    tail = [observed[s] for s in sorted(observed)][-len(schedule):]
    if tail != schedule:
        print(f"FATAL phase check: instrument announced {tail}, "
              f"intended {schedule}", flush=True)
        return 2

    base = digests[schedule[0]]
    mismatched = [k for k, d in digests.items() if d != base]
    print(f"\ntarget={args.target} fault={int(args.fault)} "
          f"top_k={args.top_k} steps={args.steps}")
    print(f"invariance across K: "
          f"{'ALL MATCH' if not mismatched else 'DIFFER at K=' + str(mismatched)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
