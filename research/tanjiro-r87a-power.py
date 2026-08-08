#!/usr/bin/env python3
"""Measured sigma and required-n for each R87-A channel.

Answers advisor r87-a-fb4's power analysis with this rig's own numbers rather
than with #457/#460/#462 priors measured on a different instrument.
"""
import json
import statistics
import sys

TOUCHED = "top8keys_r1"
EFFECTS = [6, 9, 15, 25, 60]  # us/step: my e2e priors, advisor's, A2 ceiling


def sigma_from_arms(rep, key):
    """Pooled within-arm SD across arms for one total-level channel."""
    num = den = 0.0
    for e in rep["arms"].values():
        v = e[key]["values"]
        if len(v) < 2:
            continue
        num += (len(v) - 1) * statistics.variance(v)
        den += len(v) - 1
    return (num / den) ** 0.5


def sigma_kernel(dirs, arms_report, kern):
    return None


def main() -> int:
    rep = json.load(open(sys.argv[1]))
    print(f"source: {rep['dirs']} ref={rep['ref']} runs={rep['n_runs']}\n")

    rows = []
    for key in ("wall_us", "busy_sum_us", "busy_union_us"):
        rows.append((key, sigma_from_arms(rep, key)))

    # Kernel-local sigma is recovered from the Welch CI the stats tool already
    # published for the touched kernel: ci = 1.96*sigma*sqrt(1/n1+1/n2).
    for arm, d in rep["deltas"].items():
        for r in d["per_kernel"]:
            if TOUCHED in r["kernel"]:
                n1 = rep["arms"][rep["ref"]]["n"]
                n2 = rep["arms"][arm]["n"]
                s = r["ci95_us"] / (1.96 * (1 / n1 + 1 / n2) ** 0.5)
                rows.append((f"kernel-local[{arm}] {r['kernel'][:38]}", s))

    print(f"{'channel':>52} {'sigma':>8}  " +
          "  ".join(f"n@E={e}" for e in EFFECTS))
    for name, s in rows:
        ns = []
        for e in EFFECTS:
            ns.append(f"{2 * (1.96 * s / e) ** 2:7.1f}")
        print(f"{name:>52} {s:8.2f}  " + "  ".join(ns))

    print("\nn is runs PER ARM for a two-sided 95% CI excluding zero,")
    print("n >= 2*(1.96*sigma/E)^2, cross-process design (separate worker")
    print("process per arm; knobs are read once at process start).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
