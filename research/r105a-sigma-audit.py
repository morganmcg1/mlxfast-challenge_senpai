#!/usr/bin/env python3
"""Audit two threats to the Amendment A score-primary rule (research-only).

1. Is "anti-correlation explains the score channel's tightness" informative,
   or is it an algebraic identity of the sample moments?
2. How badly would sigma_hat have to be understated (e.g. by min-variance
   channel selection at 2 dof) before the A2 REGRESSION verdict flips?

Reads research/r105a-receipts-resolved.json so it cannot drift from the
receipts.
"""
import json
import math
import pathlib
import statistics as st

HERE = pathlib.Path(__file__).resolve().parent
RESOLVED = HERE / "r105a-receipts-resolved.json"
T95 = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015}


def load():
    data = json.loads(RESOLVED.read_text())
    ctrl, treat = [], {}
    for r in data["receipts"]:
        row = {
            "arm": r["arm"],
            "S": r["official_score"],
            "nd": r["decode_speedup"],
            "np": r["prefill_speedup"],
        }
        if r["arm"].startswith("A0"):
            ctrl.append(row)
        else:
            treat.setdefault(r["arm"][:2], []).append(row)
    return ctrl, treat


def section1(ctrl):
    print("=" * 72)
    print("1. IS THE ANTI-CORRELATION EXPLANATION INFORMATIVE?")
    print("=" * 72)
    lS = [math.log(r["S"]) for r in ctrl]
    ld = [math.log(r["nd"]) for r in ctrl]
    lp = [math.log(r["np"]) for r in ctrl]
    n = len(ctrl)
    vd, vp, vS = st.variance(ld), st.variance(lp), st.variance(lS)
    md, mp = st.mean(ld), st.mean(lp)
    cov = sum((a - md) * (b - mp) for a, b in zip(ld, lp)) / (n - 1)
    r = cov / math.sqrt(vd * vp)

    withcov = 0.5625 * vd + 0.0625 * vp + 2 * 0.1875 * cov
    indep = 0.5625 * vd + 0.0625 * vp
    print(f"n={n}   sample r(ln nd, ln np) = {r:.10f}")
    print(f"  sample var(ln S)                     = {vS:.6e}")
    print(f"  0.5625 vd + 0.0625 vp + 0.375 cov    = {withcov:.6e}")
    print(f"  ratio                                = {withcov / vS:.12f}")
    print(f"  -> ln S = 0.75 ln nd + 0.25 ln np EXACTLY, so this is the")
    print(f"     bilinearity of the sample covariance operator, NOT evidence.")
    print(f"  independent-propagation var          = {indep:.6e}"
          f"   CV = {100 * math.sqrt(indep):.5f}%")
    print(f"  observed score CV                    = "
          f"{100 * math.sqrt(vS):.5f}%")
    print(f"  ratio indep/observed sd              = "
          f"{math.sqrt(indep / vS):.4f}x")
    lo, hi = fisher_ci(r, n)
    print(f"  Fisher-z 90% CI on r (n={n}, 1 dof)   = [{lo:.4f}, {hi:.4f}]")
    print("  -> the sign of the covariance is what is (weakly) established;")
    print("     the magnitude is nearly unconstrained at 1 dof.")


def fisher_ci(r, n, z=1.645):
    if n < 4:
        # Fisher z needs n-3 > 0; report the widest honest statement instead.
        return -1.0, 1.0
    zr = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n - 3)
    return math.tanh(zr - z * se), math.tanh(zr + z * se)


def section2(ctrl, treat):
    print()
    print("=" * 72)
    print("2. HOW MUCH sigma UNDERSTATEMENT OVERTURNS THE A2 REGRESSION?")
    print("=" * 72)
    S = [r["S"] for r in ctrl]
    n0 = len(S)
    sd, mean = st.stdev(S), st.mean(S)
    a2 = treat["A2"]
    n = len(a2)
    delta = st.mean(r["S"] for r in a2) - mean
    nu = (n0 - 1) + (n - 1)
    t = T95[nu]
    base = math.sqrt(1 / n + 1 / n0)
    print(f"sigma_hat(score, n0={n0}) = {sd:.10g}   mean = {mean:.10g}")
    print(f"A2 (n={n}) delta = {delta:+.10g}   nu = {nu}   t95 = {t}")
    print()
    print(f"{'sigma x':>9} {'SE':>10} {'CI90_hi':>11}  verdict")
    crit = -delta / (t * sd * base)
    for k in (1, 2, 3, 4, crit, 5, 6):
        se = sd * k * base
        hi = delta + t * se
        tag = "REGRESSION" if hi < 0 else "no longer a regression"
        mark = "  <-- critical" if abs(k - crit) < 1e-9 else ""
        print(f"{k:>9.3f} {se:>10.6f} {hi:>+11.6f}  {tag}{mark}")
    print()
    print(f"critical inflation factor = {crit:.4f}x")
    print(f"  i.e. the true sigma would have to be {crit:.2f}x the observed")
    print(f"  control spread before A2's regression becomes deniable.")
    worst = 0.2895 / (100 * sd / mean)
    print(f"  The noisiest of the six channels on these same 3 controls")
    print(f"  (step_ms, CV 0.2895%) is {worst:.2f}x the score CV, which")
    print(f"  EXCEEDS {crit:.2f}x. So a sceptic who insisted the score channel")
    print(f"  is really as noisy as the worst channel could deny it. That is")
    print(f"  why section 3, not an inflation factor, is the real defence.")


CHANS = [  # (key, higher_is_better)
    ("official_score", True),
    ("decode_speedup", True),
    ("prefill_speedup", True),
    ("prefill_ms", False),
    ("step_ms", False),
    ("cand_dec", False),
]


def _arms():
    data = json.loads(RESOLVED.read_text())
    rows = [r for r in data["receipts"]]
    ctrl = [r for r in rows if r["arm"].startswith("A0")]
    arms = {}
    for r in rows:
        if not r["arm"].startswith("A0"):
            arms.setdefault(r["arm"][:2], []).append(r)
    return ctrl, arms


def section3():
    """Channel selection is moot if an arm loses on every channel."""
    print()
    print("=" * 72)
    print("3. EVERY-CHANNEL VERDICT PER ARM (selection-free)")
    print("=" * 72)
    ctrl, arms = _arms()
    n0 = len(ctrl)
    for name, rs in sorted(arms.items()):
        n = len(rs)
        t = T95[(n0 - 1) + (n - 1)]
        base = math.sqrt(1 / n + 1 / n0)
        print(f"\n-- {name} (n={n}, nu={(n0 - 1) + (n - 1)}, t95={t}) --")
        print(f"{'channel':>16} {'ctrl mean':>12} {'sigma':>10} {'CV%':>7} "
              f"{'delta':>11} {'z':>8}  direction")
        for key, up in CHANS:
            vals = [r[key] for r in ctrl]
            m, sd = st.mean(vals), st.stdev(vals)
            d = st.mean(r[key] for r in rs) - m
            se = sd * base
            good = (d > 0) if up else (d < 0)
            hi = d + t * se if up else d - t * se
            sig = (hi < 0) if up else (hi > 0)
            tag = "better" if good else "worse"
            if sig:
                tag = ("BETTER" if good else "WORSE") + " (CI90 excludes 0)"
            print(f"{key:>16} {m:>12.6f} {sd:>10.6f} {100 * sd / m:>7.4f} "
                  f"{d:>+11.6f} {d / se:>+8.2f}  {tag}")


def section4():
    """Split each speedup delta into candidate-side and baseline-side parts.

    A published speedup is baseline/candidate measured in the same session.
    Only the candidate limb is under my control; a change in the baseline limb
    is session noise that the pairing was supposed to remove.
    """
    print()
    print("=" * 72)
    print("4. CANDIDATE-SIDE vs BASELINE-SIDE ATTRIBUTION")
    print("=" * 72)
    print("A published speedup is baseline/candidate in the same session. My")
    print("edit cannot move the baseline limb, so any baseline-limb movement is")
    print("session noise, and only the candidate limbs carry a causal effect.")
    ctrl, arms = _arms()
    n0 = len(ctrl)
    base = math.sqrt(1 / 1 + 1 / n0)
    limbs = ["baseline_pre", "cand_pre", "baseline_dec", "cand_dec"]

    print()
    print(f"{'arm':>6} {'base_pre':>11} {'cand_pre':>11} "
          f"{'base_dec':>11} {'cand_dec':>11} {'step_ms':>9}")
    allrows = ctrl + [r for rs in arms.values() for r in rs]
    for r in allrows:
        print(f"{r['arm']:>6} {r['baseline_pre']:>11.7f} "
              f"{r['cand_pre']:>11.7f} {r['baseline_dec']:>11.7f} "
              f"{r['cand_dec']:>11.7f} {r['step_ms']:>9.5f}")

    for name, rs in sorted(arms.items()):
        n = len(rs)
        b = math.sqrt(1 / n + 1 / n0)
        t = T95[(n0 - 1) + (n - 1)]
        print(f"\n-- {name} limbs (n={n}) --")
        print(f"{'limb':>13} {'ctrl mean':>12} {'sigma':>11} {'CV%':>7} "
              f"{'delta':>12} {'z':>8}  causal?")
        for key in limbs:
            vals = [r[key] for r in ctrl]
            m, sd = st.mean(vals), st.stdev(vals)
            d = st.mean(r[key] for r in rs) - m
            z = d / (sd * b)
            own = "candidate" if key.startswith("cand") else "SESSION NOISE"
            flag = " *" if abs(z) > t else ""
            print(f"{key:>13} {m:>12.7f} {sd:>11.7f} {100 * sd / m:>7.4f} "
                  f"{d:>+12.7f} {z:>+8.2f}  {own}{flag}")

        S = st.mean(r["official_score"] for r in ctrl)
        dnd = math.log(st.mean(r["decode_speedup"] for r in rs)
                       / st.mean(r["decode_speedup"] for r in ctrl))
        dnp = math.log(st.mean(r["prefill_speedup"] for r in rs)
                       / st.mean(r["prefill_speedup"] for r in ctrl))
        tot = 0.75 * dnd + 0.25 * dnp
        print(f"  score delta split (dlnS = .75 dln nd + .25 dln np):")
        print(f"    decode  0.75 * {dnd:+.6f} = {0.75 * dnd:+.6f}"
              f"  ({100 * 0.75 * dnd / tot:5.1f}% of dlnS)")
        print(f"    prefill 0.25 * {dnp:+.6f} = {0.25 * dnp:+.6f}"
              f"  ({100 * 0.25 * dnp / tot:5.1f}% of dlnS)")
        print(f"    total dlnS = {tot:+.6f}  ->  dS = {S * tot:+.7f}")
    print()
    print("Rows marked * exceed the t95 threshold. A '*' on a SESSION NOISE")
    print("row means the pairing imported drift the treatment cannot cause.")


def main():
    ctrl, treat = load()
    section1(ctrl)
    section2(ctrl, treat)
    section3()
    section4()


if __name__ == "__main__":
    main()
