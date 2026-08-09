#!/usr/bin/env python3
"""R93-B nested variance-components decomposition (research only).

Reads the per-process JSON files written by `fern_r93_nested_probe.py` and
separates

    sigma^2_process   between worker processes
    sigma^2_run       between `decode_begin` runs inside one process
    sigma^2_step      between decode steps inside one run

then turns those into the standard error of every contrast the campaign can
actually build, so a protocol can be costed before it is run.

  python3 research/fern_r93_variance.py /tmp/r93/stage1/*.json

Step times are heavy-tailed and autocorrelated, so the script reports the plain
mean-based decomposition, a trimmed-mean version, and an autocorrelation-aware
effective sample size for the step channel. CIs come from a nested nonparametric
bootstrap that resamples processes, then runs, then steps.
"""
import argparse
import json
import math
import random
import statistics
import sys


def trimmed(xs, frac):
    if frac <= 0:
        return list(xs)
    xs = sorted(xs)
    k = int(len(xs) * frac)
    return xs[k:len(xs) - k] if len(xs) - 2 * k > 2 else xs


def anova_components(cells):
    """Balanced nested random-effects decomposition.

    `cells[p][r]` is the list of step values for run r of process p. Returns
    (var_process, var_run, var_step, grand_mean, ms) using the classical
    expected-mean-square estimators; negative components are reported as-is so
    a genuinely absent level is visible rather than silently clamped.
    """
    P = len(cells)
    R = min(len(c) for c in cells)
    S = min(len(run) for c in cells for run in c)
    run_means = [[statistics.fmean(cells[p][r][:S]) for r in range(R)] for p in range(P)]
    proc_means = [statistics.fmean(run_means[p]) for p in range(P)]
    grand = statistics.fmean(proc_means)

    ss_step = sum((v - run_means[p][r]) ** 2
                  for p in range(P) for r in range(R) for v in cells[p][r][:S])
    ss_run = S * sum((run_means[p][r] - proc_means[p]) ** 2
                     for p in range(P) for r in range(R))
    ss_proc = R * S * sum((m - grand) ** 2 for m in proc_means)

    df_step = P * R * (S - 1)
    df_run = P * (R - 1)
    df_proc = P - 1
    ms_step = ss_step / df_step
    ms_run = ss_run / df_run if df_run else float("nan")
    ms_proc = ss_proc / df_proc if df_proc else float("nan")

    var_step = ms_step
    var_run = (ms_run - ms_step) / S
    var_proc = (ms_proc - ms_run) / (R * S)
    return var_proc, var_run, var_step, grand, {
        "ms_step": ms_step, "ms_run": ms_run, "ms_proc": ms_proc,
        "df_step": df_step, "df_run": df_run, "df_proc": df_proc,
        "P": P, "R": R, "S": S,
    }


def autocorr_ess(series, max_lag=50):
    """Integrated-autocorrelation effective sample size for one run's steps."""
    n = len(series)
    mu = statistics.fmean(series)
    dev = [x - mu for x in series]
    denom = sum(d * d for d in dev)
    if denom <= 0:
        return n, 0.0, []
    rho = []
    tau = 1.0
    for lag in range(1, min(max_lag, n // 4) + 1):
        num = sum(dev[i] * dev[i + lag] for i in range(n - lag))
        r = num / denom
        rho.append(r)
        if r <= 0:
            break
        tau += 2 * r
    return n / tau, tau, rho


def nested_bootstrap(cells, B, rng):
    out = []
    P = len(cells)
    for _ in range(B):
        boot = []
        for _ in range(P):
            p = rng.randrange(P)
            runs = cells[p]
            R = len(runs)
            bruns = []
            for _ in range(R):
                r = rng.randrange(R)
                steps = runs[r]
                S = len(steps)
                bruns.append([steps[rng.randrange(S)] for _ in range(S)])
            boot.append(bruns)
        try:
            vp, vr, vs, g, _ = anova_components(boot)
        except (statistics.StatisticsError, ZeroDivisionError):
            continue
        out.append((vp, vr, vs, g))
    return out


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def sd(v):
    return math.sqrt(v) if v > 0 else -math.sqrt(-v)


def drift(cells):
    """Per-run OLS slope of step time on step index, in us per step index."""
    slopes = []
    for p, runs in enumerate(cells):
        for r, steps in enumerate(runs):
            n = len(steps)
            xbar = (n - 1) / 2
            ybar = statistics.fmean(steps)
            sxx = sum((i - xbar) ** 2 for i in range(n))
            sxy = sum((i - xbar) * (steps[i] - ybar) for i in range(n))
            b = sxy / sxx
            resid = [steps[i] - (ybar + b * (i - xbar)) for i in range(n)]
            se = math.sqrt(sum(e * e for e in resid) / (n - 2) / sxx)
            slopes.append((p, r, b, se, ybar))
    return slopes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--drop-steps", type=int, default=10,
                    help="leading steps discarded from every run as warmup")
    ap.add_argument("--drop-warmup-runs", action="store_true", default=True)
    ap.add_argument("--keep-warmup-runs", dest="drop_warmup_runs",
                    action="store_false")
    ap.add_argument("--glue", type=int, default=None,
                    help="keep only steps at this glue depth")
    ap.add_argument("--trim", type=float, default=0.0,
                    help="two-sided trim fraction applied inside each run")
    ap.add_argument("--label-contains", default=None,
                    help="keep only processes whose label contains this")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=93)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    cells = []
    labels = []
    hashes = set()
    mism = 0
    for path in sorted(args.files):
        with open(path) as fh:
            doc = json.load(fh)
        if args.label_contains and args.label_contains not in (doc.get("label") or ""):
            continue
        hashes.update(doc["token_stream_hashes"])
        mism += doc.get("teacher_forced_mismatches", 0)
        by_run = {}
        for rec in doc["records"]:
            if args.drop_warmup_runs and rec.get("warmup_run"):
                continue
            if rec["step"] < args.drop_steps:
                continue
            if args.glue is not None and rec["glue"] != args.glue:
                continue
            by_run.setdefault(rec["run"], []).append(rec["us"])
        if not by_run:
            continue
        runs = [by_run[k] for k in sorted(by_run)]
        if args.trim:
            runs = [trimmed(r, args.trim) for r in runs]
        cells.append(runs)
        labels.append(doc.get("label") or path)

    if len(cells) < 2:
        raise SystemExit("need at least two processes")

    print(f"token_stream_hashes={sorted(hashes)} teacher_forced_mismatches={mism}")
    if len(hashes) != 1:
        print("WARNING: token stream is not identical across all processes")

    vp, vr, vs, grand, ms = anova_components(cells)
    P, R, S = ms["P"], ms["R"], ms["S"]
    print(f"\ndesign: P={P} processes x R={R} runs x S={S} steps "
          f"(after dropping {args.drop_steps} warmup steps/run"
          + (", warmup runs" if args.drop_warmup_runs else "") + ")")
    print(f"grand mean step time: {grand:.1f} us")
    print(f"MS_process={ms['ms_proc']:.1f} (df {ms['df_proc']})  "
          f"MS_run={ms['ms_run']:.1f} (df {ms['df_run']})  "
          f"MS_step={ms['ms_step']:.1f} (df {ms['df_step']})")

    rng = random.Random(args.seed)
    boots = nested_bootstrap(cells, args.bootstrap, rng)
    b_vp = [b[0] for b in boots]
    b_vr = [b[1] for b in boots]
    b_vs = [b[2] for b in boots]

    print("\nvariance components (us/step):")
    for name, v, bs in (("sigma_process", vp, b_vp),
                        ("sigma_run|process", vr, b_vr),
                        ("sigma_step|run", vs, b_vs)):
        lo, hi = pct(bs, 0.025), pct(bs, 0.975)
        print(f"  {name:<18} sd={sd(v):9.2f}  95% CI [{sd(lo):9.2f}, {sd(hi):9.2f}]")

    taus = []
    for runs in cells:
        for steps in runs:
            ess, tau, _ = autocorr_ess(steps)
            taus.append(tau)
    tau_med = statistics.median(taus)
    print(f"\nstep autocorrelation: median tau={tau_med:.2f} "
          f"(ESS per run = S/tau = {S/tau_med:.0f} of {S})")

    vs_eff = vs * tau_med
    print(f"  autocorrelation-inflated step variance for run means: "
          f"sd_eff={sd(vs_eff):.1f} us")

    def se_run_mean(s=S):
        return math.sqrt(max(vs_eff, 0) / s)

    def se_proc_mean(r=R, s=S):
        return math.sqrt(max(vr, 0) / r + max(vs_eff, 0) / (r * s))

    def se_grand(p=P, r=R, s=S):
        return math.sqrt(max(vp, 0) / p + max(vr, 0) / (p * r)
                         + max(vs_eff, 0) / (p * r * s))

    print(f"\nimplied SEs at the observed design (P={P},R={R},S={S}):")
    print(f"  SE(run mean)             = {se_run_mean():8.2f} us")
    print(f"  SE(process mean)         = {se_proc_mean():8.2f} us")
    print(f"  SE(grand mean)           = {se_grand():8.2f} us")

    print("\nSE of a PAIRED A-B contrast, by the level the arm can switch at:")
    for level, f in (
        ("step-paired  (n=pairs)", lambda n: math.sqrt(2 * max(vs_eff, 0) / n)),
        ("run-paired   (n=pairs)",
         lambda n: math.sqrt(2 * (max(vr, 0) + max(vs_eff, 0) / S) / n)),
        ("process-paired(n=pairs)",
         lambda n: math.sqrt(2 * (max(vp, 0) + max(vr, 0) / R
                                  + max(vs_eff, 0) / (R * S)) / n)),
    ):
        row = "  ".join(f"n={n}:{f(n):7.2f}" for n in (1, 4, 8, 16, 64, 256))
        print(f"  {level:<24} {row}")

    print("\nwithin-run drift (OLS us per step index):")
    slopes = drift(cells)
    bs = [s[2] for s in slopes]
    pos = sum(1 for b in bs if b > 0)
    print(f"  runs={len(bs)} median={statistics.median(bs):+.3f} "
          f"mean={statistics.fmean(bs):+.3f} "
          f"sd={statistics.pstdev(bs):.3f} positive={pos}/{len(bs)}")
    print(f"  implied drift across a {S}-step run: "
          f"{statistics.median(bs)*S:+.1f} us end-to-end")
    for p, r, b, se, ybar in slopes[:12]:
        print(f"    p{p} r{r}: slope={b:+.3f} +/- {se:.3f} mean={ybar:.1f}")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump({
                "P": P, "R": R, "S": S, "grand_us": grand,
                "sd_process": sd(vp), "sd_run": sd(vr), "sd_step": sd(vs),
                "sd_process_ci": [sd(pct(b_vp, 0.025)), sd(pct(b_vp, 0.975))],
                "sd_run_ci": [sd(pct(b_vr, 0.025)), sd(pct(b_vr, 0.975))],
                "sd_step_ci": [sd(pct(b_vs, 0.025)), sd(pct(b_vs, 0.975))],
                "tau": tau_med, "sd_step_eff": sd(vs_eff),
                "se_run_mean": se_run_mean(), "se_proc_mean": se_proc_mean(),
                "se_grand": se_grand(),
                "drift_median_us_per_step": statistics.median(bs),
                "drift_sd": statistics.pstdev(bs),
                "token_stream_hashes": sorted(hashes),
            }, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
