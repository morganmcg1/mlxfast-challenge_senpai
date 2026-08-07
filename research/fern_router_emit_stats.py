#!/usr/bin/env python3
"""PR #204 router-emit A/B statistics (research-only).

Reads the per-step millisecond dumps written by research/fern_router_emit_ab.sh
and reports the paired arm contrast.

The unit of replication is the *run*, not the step: steps inside one worker
process share its clock state, page mapping and thermal history, so pooling
steps across runs would understate the real between-run scatter. Each run is
reduced to its median step, and the arm contrast is taken over run medians.

  python3 research/fern_router_emit_stats.py OUTDIR
"""
import argparse
import pathlib
import statistics
import sys

# The first steps of a run pay one-time KV growth and JIT/pipeline warmup on
# the full-attention layers, so they are not part of the steady decode regime
# the benchmark scores.
WARMUP_STEPS = 16

LABELS = {
    "A": "emit sink (candidate)",
    "B": "standalone dispatch (base)",
    "C": "emit kernel + standalone kept",
}


def load(path: pathlib.Path):
    vals = [float(line) for line in path.read_text().split() if line.strip()]
    return vals[WARMUP_STEPS:]


def main() -> int:
    global WARMUP_STEPS

    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--warmup", type=int, default=WARMUP_STEPS)
    args = ap.parse_args()

    WARMUP_STEPS = args.warmup

    runs = sorted(pathlib.Path(args.outdir).glob("*.steps.txt"))
    if not runs:
        print(f"no *.steps.txt under {args.outdir}", file=sys.stderr)
        return 1

    arms = {"A": [], "B": [], "C": []}
    print(f"{'run':<12} {'arm':<4} {'n':>6} {'median_ms':>11} {'mean_ms':>10} "
          f"{'p10_ms':>9} {'p90_ms':>9}")
    for path in runs:
        tag = path.name[: -len(".steps.txt")]
        arm = tag.rsplit(".", 1)[-1]
        vals = load(path)
        med = statistics.median(vals)
        ordered = sorted(vals)
        print(f"{tag:<12} {arm:<4} {len(vals):>6} {med:>11.4f} "
              f"{statistics.mean(vals):>10.4f} "
              f"{ordered[len(ordered)//10]:>9.4f} "
              f"{ordered[9*len(ordered)//10]:>9.4f}")
        arms[arm].append(med)

    print()
    summary = {}
    for arm, meds in arms.items():
        if not meds:
            continue
        m = statistics.median(meds)
        sd = statistics.stdev(meds) if len(meds) > 1 else float("nan")
        summary[arm] = (m, sd, len(meds))
        print(f"arm {arm} {LABELS[arm]:<34} runs={len(meds)} "
              f"median_of_medians={m*1e3:.1f} us  "
              f"between_run_sd={sd*1e3:.1f} us  "
              f"medians={[round(v*1e3, 1) for v in meds]}")

    # A-B is the end-to-end verdict; C isolates the emit kernel's own cost
    # (C-B, dispatch count held fixed) from the dispatch saving (A-C).
    for lhs, rhs, what in (("A", "B", "end-to-end (emit sink vs base)"),
                           ("C", "B", "emit-kernel overhead alone"),
                           ("A", "C", "39 standalone dispatches removed")):
        if lhs not in summary or rhs not in summary:
            continue
        delta = summary[lhs][0] - summary[rhs][0]
        base = summary["B"][0]
        print()
        print(f"{lhs} - {rhs}  [{what}] = {delta*1e3:+.1f} us/step "
              f"({delta/base*100:+.3f} % of base decode step)")
        # Pair the i-th run of each arm in run order so every pair spans a
        # short, drift-balanced window inside the palindromic block.
        n = min(len(arms[lhs]), len(arms[rhs]))
        diffs = [arms[lhs][i] - arms[rhs][i] for i in range(n)]
        if n > 1:
            dm = statistics.mean(diffs)
            dsd = statistics.stdev(diffs)
            print(f"  paired diffs (us): {[round(d*1e3, 1) for d in diffs]}")
            print(f"  paired mean = {dm*1e3:+.1f} us, sd = {dsd*1e3:.1f} us, "
                  f"sem = {dsd/(n ** 0.5)*1e3:.1f} us, n = {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
