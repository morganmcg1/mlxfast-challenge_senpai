#!/usr/bin/env python3
"""R125-E analysis: drift-corrected per-arm decode deltas from arm-driver TSVs.

The driver runs one worker process per arm in a counterbalanced order, so the
only nuisance left is slow host drift across a pass. Every arm run is therefore
compared against the control level interpolated between the nearest earlier and
later `C` runs of the same pass, which removes a linear drift term without
spending a control run next to every arm.

  python3 research/frieren_r125e_analyze.py /tmp/r125e/p1_runs.tsv ...
  python3 research/frieren_r125e_analyze.py --confirm FUS /tmp/r125e/cf_runs.tsv
"""
import argparse
import random
import statistics
import sys

US_PER_MS = 1000.0
PCT_SCORE_PER_US = 0.00586  # 1 us/step of decode == 0.00586 % of score


def load(paths):
    runs = []
    for p in paths:
        with open(p) as fh:
            for line in fh:
                f = line.rstrip("\n").split("\t")
                if len(f) < 10 or f[0] == "tag":
                    continue
                tag, run, arm = f[0], int(f[1]), f[2]
                if run == 0:
                    continue  # unscored warm-up (cold caches, thermal ramp)
                med, mean, div, rc = f[4], f[5], f[6], f[9]
                if med == "NA" or rc != "0":
                    print(f"skip bad run {tag}/{run}/{arm} rc={rc} med={med}", file=sys.stderr)
                    continue
                runs.append(
                    dict(tag=tag, run=run, arm=arm, median=float(med),
                         mean=float(mean), div=div)
                )
    runs.sort(key=lambda r: (r["tag"], r["run"]))
    return runs


def control_interp(runs):
    """attach ctrl (interpolated control median) to every run of a pass"""
    for tag in sorted({r["tag"] for r in runs}):
        pas = [r for r in runs if r["tag"] == tag]
        ctrl = [(r["run"], r["median"]) for r in pas if r["arm"] == "C"]
        if not ctrl:
            raise SystemExit(f"pass {tag} has no control run")
        for r in pas:
            x = r["run"]
            lo = [c for c in ctrl if c[0] <= x]
            hi = [c for c in ctrl if c[0] >= x]
            if not lo:
                r["ctrl"] = hi[0][1]
            elif not hi:
                r["ctrl"] = lo[-1][1]
            else:
                (x0, y0), (x1, y1) = lo[-1], hi[0]
                r["ctrl"] = y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            r["delta_us"] = (r["median"] - r["ctrl"]) * US_PER_MS
    return runs


def screen(runs):
    control_interp(runs)
    arms = {}
    for r in runs:
        arms.setdefault(r["arm"], []).append(r)
    rows = []
    for arm, rs in arms.items():
        d = [r["delta_us"] for r in rs]
        rows.append(dict(
            arm=arm, n=len(d), mean_us=statistics.fmean(d),
            per_pass=[(r["tag"], round(r["delta_us"], 1)) for r in rs],
            med_ms=statistics.fmean([r["median"] for r in rs]),
            div={r["div"] for r in rs},
        ))
    rows.sort(key=lambda r: r["mean_us"])
    print(f"{'arm':7} {'n':>2} {'mean_dus':>9} {'%score':>7} {'median_ms':>9}  per-pass delta_us")
    for r in rows:
        pct = -r["mean_us"] * PCT_SCORE_PER_US
        div = "" if r["div"] <= {"0"} else f"  DIVERGENCE={sorted(r['div'])}"
        print(f"{r['arm']:7} {r['n']:2d} {r['mean_us']:9.1f} {pct:+7.3f} {r['med_ms']:9.4f}  "
              f"{r['per_pass']}{div}")


def confirm(arm, runs, iters=20000, seed=20260811):
    """paired control-vs-arm bootstrap on interleaved ABBA runs"""
    control_interp(runs)
    a = [r for r in runs if r["arm"] == arm]
    c = [r for r in runs if r["arm"] == "C"]
    if not a:
        raise SystemExit(f"no runs for arm {arm}")
    deltas = [r["delta_us"] for r in a]
    rng = random.Random(seed)
    boot = []
    for _ in range(iters):
        boot.append(statistics.fmean([rng.choice(deltas) for _ in deltas]))
    boot.sort()

    def ci(alpha):
        return boot[int(alpha / 2 * iters)], boot[int((1 - alpha / 2) * iters)]

    lo, hi = ci(0.05)
    blo, bhi = ci(0.05 / 3)  # Bonferroni over the pre-registered k=3 confirm family
    point = statistics.fmean(deltas)
    csd = statistics.stdev([r["median"] for r in c]) * US_PER_MS if len(c) > 1 else float("nan")
    print(f"arm={arm} n_arm={len(a)} n_ctrl={len(c)}")
    print(f"  control medians (ms): {[round(r['median'], 4) for r in c]}")
    print(f"  arm     medians (ms): {[round(r['median'], 4) for r in a]}")
    print(f"  paired delta_us per run: {[round(d, 1) for d in deltas]}")
    print(f"  point {point:+.1f} us/step  95% CI [{lo:+.1f}, {hi:+.1f}]  "
          f"score {-point * PCT_SCORE_PER_US:+.3f} % "
          f"[{-hi * PCT_SCORE_PER_US:+.3f}, {-lo * PCT_SCORE_PER_US:+.3f}]")
    print(f"  Bonferroni k=3 (98.3%) CI [{blo:+.1f}, {bhi:+.1f}] us/step  "
          f"score [{-bhi * PCT_SCORE_PER_US:+.3f}, {-blo * PCT_SCORE_PER_US:+.3f}] %")
    print(f"  control run-to-run sd: {csd:.1f} us/step  "
          f"achieved floor 2sd/sqrt(n) = {2 * csd / len(a) ** 0.5:.1f} us/step "
          f"= {2 * csd / len(a) ** 0.5 * PCT_SCORE_PER_US:.3f} % score")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="+")
    ap.add_argument("--confirm", metavar="ARM")
    args = ap.parse_args()
    runs = load(args.tsv)
    if args.confirm:
        confirm(args.confirm, runs)
    else:
        screen(runs)


if __name__ == "__main__":
    main()
