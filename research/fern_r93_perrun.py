#!/usr/bin/env python3
"""R93-B switching-free validation arm (research only, not part of the submission).

The ladder estimator changes K between adjacent steps. That is what makes it
sharp, but it also means every ladder delta is measured on a decode step whose
predecessor had a different K. `perrun:A,B` holds K constant for a whole
`decode_begin` run and alternates only between runs, so it shares no ordering
artefact with the ladder at all. If the two agree, no per-step switching
artefact is inflating or deflating the ladder slope.

Preregistered decision rule 6 (research/fern-r93-stage3-preregistration.md):
the run-paired K=240 - K=0 contrast must agree with 240x the ladder slope.

  python3 research/fern_r93_perrun.py '/tmp/r93/stage3/p*.json' \
      --label-contains perrun --json-out /tmp/r93/stage3_perrun.json

Adjacent runs inside one process are paired, so a between-run level shift that
is common to a process cancels exactly the way the ladder's block mean does.
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import statistics
import sys


def pct(xs, q):
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def ci(xs):
    return pct(xs, 0.025), pct(xs, 0.975)


def load(files, drop_steps, keep_warmup_runs, label_contains):
    """-> list[process] of list[(depth, [us, ...])] in run order."""
    procs, hashes, mism = [], set(), 0
    for path in sorted(files):
        with open(path) as fh:
            doc = json.load(fh)
        if label_contains and label_contains not in doc.get("label", ""):
            continue
        hashes.update(doc.get("token_stream_hashes", []))
        mism += doc.get("teacher_forced_mismatches", 0)
        by_run = {}
        for rec in doc["records"]:
            if not keep_warmup_runs and rec.get("warmup_run"):
                continue
            if rec["step"] < drop_steps:
                continue
            by_run.setdefault(rec["run"], []).append(rec)
        runs = []
        for key in sorted(by_run):
            steps = by_run[key]
            depths = {r["k"] for r in steps}
            if len(depths) != 1:
                raise SystemExit(f"{path} run {key} is not switching-free")
            runs.append((depths.pop(), [r["us"] for r in steps]))
        if runs:
            procs.append(runs)
    return procs, hashes, mism


def censored_mean(us, mad_mult):
    med = statistics.median(us)
    dev = statistics.median([abs(u - med) for u in us]) * 1.4826
    if dev <= 0:
        return statistics.mean(us), 0
    keep = [u for u in us if abs(u - med) <= mad_mult * dev]
    return statistics.mean(keep), len(us) - len(keep)


def pair(procs, lo_k, hi_k, mad_mult, censor):
    """Adjacent-run differences (hi - lo) inside each process."""
    out = []
    for runs in procs:
        means = []
        for depth, us in runs:
            m = censored_mean(us, mad_mult)[0] if censor else statistics.mean(us)
            means.append((depth, m))
        proc_pairs = []
        for i in range(len(means) - 1):
            (ka, ma), (kb, mb) = means[i], means[i + 1]
            if {ka, kb} != {lo_k, hi_k}:
                continue
            proc_pairs.append(mb - ma if kb == hi_k else ma - mb)
        if proc_pairs:
            out.append(proc_pairs)
    return out


def resample(pairs, rng):
    procs = [pairs[rng.randrange(len(pairs))] for _ in pairs]
    return [p[rng.randrange(len(p))] for p in procs for _ in p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--drop-steps", type=int, default=24)
    ap.add_argument("--keep-warmup-runs", action="store_true")
    ap.add_argument("--label-contains", default="perrun")
    ap.add_argument("--lo", type=int, default=0)
    ap.add_argument("--hi", type=int, default=240)
    ap.add_argument("--mad-mult", type=float, default=8.0)
    ap.add_argument("--no-censor", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=93)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    files = []
    for f in args.files:
        files.extend(glob.glob(f))
    procs, hashes, mism = load(files, args.drop_steps,
                               args.keep_warmup_runs, args.label_contains)
    if not procs:
        raise SystemExit("no switching-free processes matched")

    pairs = pair(procs, args.lo, args.hi, args.mad_mult, not args.no_censor)
    flat = [d for p in pairs for d in p]
    if not flat:
        raise SystemExit(f"no adjacent K={args.lo}/K={args.hi} run pairs")

    rng = random.Random(args.seed)
    bs = [statistics.mean(resample(pairs, rng)) for _ in range(args.bootstrap)]
    lo, hi = ci(bs)
    est = statistics.mean(flat)
    per = est / (args.hi - args.lo)
    plo, phi = lo / (args.hi - args.lo), hi / (args.hi - args.lo)

    print(f"processes={len(procs)} run-pairs={len(flat)} "
          f"hashes={sorted(hashes)} mismatches={mism}")
    print(f"K={args.hi} - K={args.lo}: {est:+.2f} us/step "
          f"[{lo:+.2f}, {hi:+.2f}]  se={statistics.pstdev(bs):.2f}")
    print(f"implied {per:+.4f} us/dispatch [{plo:+.4f}, {phi:+.4f}]")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump({
                "n_processes": len(procs), "n_run_pairs": len(flat),
                "lo_k": args.lo, "hi_k": args.hi,
                "delta_us_per_step": est, "delta_ci": [lo, hi],
                "delta_se": statistics.pstdev(bs),
                "us_per_dispatch": per, "us_per_dispatch_ci": [plo, phi],
                "censored": not args.no_censor,
                "token_stream_hashes": sorted(hashes),
                "teacher_forced_mismatches": mism,
            }, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
