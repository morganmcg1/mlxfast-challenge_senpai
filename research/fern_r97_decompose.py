#!/usr/bin/env python3
"""R97-A Stage 2: split the measured three-rung ladder into a byte term and an
unpack-ALU term (research only, not submitted).

The two compacted planes differ sharply in how many integer ops they add per
byte they remove (gate/up 18.3, down 50.0), so the two block-paired contrasts
identify both unknowns without any extra experimental arm:

    d1 = mean(rung1) - mean(rung0) = -v * B1 + c * N1      # gate/up
    d2 = mean(rung2) - mean(rung1) = -v * B2 + c * N2      # down

with v the marginal value of a removed megabyte (us/MB) and c the marginal cost
of a million added integer ops (us/Mop). R* = v / c is then the break-even
"added integer ops per byte removed" that any future byte-removing decode change
can be screened against before it is built.

Assumes the two effects enter additively and that bytes and unpack ops are the
only systematic difference between rungs. Stream-splitting cost is not separable
from c here and is reported as part of it.

    python3 research/fern_r97_decompose.py '/tmp/r97/ladder/p*.json' \
        --drop-steps 24 --bootstrap 4000 --seed 97 --json-out out.json
"""
import argparse
import glob
import json
import statistics


# Plane constants, from the preregistration byte model and the §3c op audit.
B1_MB = 16.070912   # gate/up bytes removed per step
B2_MB = 4.192256    # down bytes removed per step (marginal, S2b - S2a)
N1_MOP = 293.6      # gate/up added integer ops per step, millions
N2_MOP = 209.7      # down added integer ops per step, millions


def load_cells(patterns, drop_steps, keep_warmup_runs, include_placebo):
    """Return {(process, run, block): {rung: [us, ...]}} and doc-level checks."""
    cells = {}
    hashes, mismatches, files = set(), 0, []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            files.append(path)
            doc = json.load(open(path))
            hashes.update(doc.get("token_stream_hashes") or [])
            mismatches += int(doc.get("teacher_forced_mismatches") or 0)
            for rec in doc["records"]:
                if rec.get("warmup_run") and not keep_warmup_runs:
                    continue
                if rec.get("placebo") and not include_placebo:
                    continue
                if not rec.get("placebo") and include_placebo:
                    continue
                if rec["step"] < drop_steps:
                    continue
                key = (rec["process"], rec["run"], rec["block"])
                # A placebo block executes rung 0 on every step, so the only
                # label that varies is the rung each step was assigned to.
                rung = rec["slot"] if include_placebo else rec["glue"]
                cells.setdefault(key, {}).setdefault(rung, []).append(rec["us"])
    return cells, sorted(hashes), mismatches, files


def block_contrasts(cells, rungs=(0, 1, 2)):
    """One (d1, d2) pair per block that saw every rung, using cell medians."""
    out = []
    for key, byrung in sorted(cells.items()):
        if not all(r in byrung and byrung[r] for r in rungs):
            continue
        med = {r: statistics.median(byrung[r]) for r in rungs}
        out.append((key[0], med[1] - med[0], med[2] - med[1], med))
    return out


def solve(d1, d2):
    """Solve the 2x2 system for v (us/MB) and c (us/Mop)."""
    det = (-B1_MB) * N2_MOP - N1_MOP * (-B2_MB)
    if abs(det) < 1e-12:
        return float("nan"), float("nan")
    v = (d1 * N2_MOP - d2 * N1_MOP) / det
    c = ((-B1_MB) * d2 - (-B2_MB) * d1) / det
    return v, c


def summarise(contrasts, n_boot, seed):
    import random

    rng = random.Random(seed)
    d1 = statistics.fmean(c[1] for c in contrasts)
    d2 = statistics.fmean(c[2] for c in contrasts)
    v, c = solve(d1, d2)

    # Cluster the resample on process so between-host drift is not treated as
    # independent replication.
    by_proc = {}
    for row in contrasts:
        by_proc.setdefault(row[0], []).append(row)
    procs = sorted(by_proc)

    draws = {"d1": [], "d2": [], "v": [], "c": [], "rstar": [], "saved": []}
    for _ in range(n_boot):
        rows = []
        for _ in procs:
            block = by_proc[rng.choice(procs)]
            rows.extend(rng.choice(block) for _ in range(len(block)))
        if not rows:
            continue
        b1 = statistics.fmean(r[1] for r in rows)
        b2 = statistics.fmean(r[2] for r in rows)
        bv, bc = solve(b1, b2)
        draws["d1"].append(b1)
        draws["d2"].append(b2)
        draws["v"].append(bv)
        draws["c"].append(bc)
        draws["rstar"].append(bv / bc if bc else float("nan"))
        draws["saved"].append(-(b1 + b2))

    def ci(name):
        vals = sorted(x for x in draws[name] if x == x)
        if not vals:
            return [float("nan"), float("nan")]
        lo = vals[max(0, int(0.025 * len(vals)) - 1)]
        hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
        return [lo, hi]

    return {
        "n_blocks": len(contrasts),
        "n_processes": len(procs),
        "d1_us_gate_up": d1,
        "d1_ci": ci("d1"),
        "d2_us_down": d2,
        "d2_ci": ci("d2"),
        "s2b_total_us": d1 + d2,
        "s2b_saved_us": -(d1 + d2),
        "s2b_saved_ci": ci("saved"),
        "byte_value_us_per_mb": v,
        "byte_value_ci": ci("v"),
        "implied_bandwidth_gb_s": (1000.0 / v) if v else float("nan"),
        "op_cost_us_per_mop": c,
        "op_cost_ci": ci("c"),
        "implied_int_throughput_tops": (1.0 / c) if c else float("nan"),
        "rstar_ops_per_byte": (v / c) if c else float("nan"),
        "rstar_ci": ci("rstar"),
        "design_ops_per_byte_gate_up": N1_MOP / B1_MB,
        "design_ops_per_byte_down": N2_MOP / B2_MB,
        "design_ops_per_byte_s2b": (N1_MOP + N2_MOP) / (B1_MB + B2_MB),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--drop-steps", type=int, default=24)
    ap.add_argument("--keep-warmup-runs", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=97)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    cells, hashes, mismatches, files = load_cells(
        args.patterns, args.drop_steps, args.keep_warmup_runs, False
    )
    contrasts = block_contrasts(cells)
    if not contrasts:
        raise SystemExit("no block saw all three rungs")
    res = summarise(contrasts, args.bootstrap, args.seed)
    res["files"] = len(files)
    res["token_stream_hashes"] = hashes
    res["teacher_forced_mismatches"] = mismatches

    pcells, _, _, _ = load_cells(
        args.patterns, args.drop_steps, args.keep_warmup_runs, True
    )
    pc = block_contrasts(pcells)
    res["placebo_blocks"] = len(pc)
    if pc:
        psum = summarise(pc, args.bootstrap, args.seed)
        res["placebo_d1_us"] = psum["d1_us_gate_up"]
        res["placebo_d1_ci"] = psum["d1_ci"]
        res["placebo_d2_us"] = psum["d2_us_down"]
        res["placebo_d2_ci"] = psum["d2_ci"]

    print(json.dumps(res, indent=2, sort_keys=True))
    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(res, fh, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
