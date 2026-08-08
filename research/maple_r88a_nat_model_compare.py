#!/usr/bin/env python3
"""Research-only (PR #473): does the shipped dispatch regime reproduce the
SPLIT=1 per-kernel give-back?

The natural (shipped) regime groups many kernels into one command buffer, so
the GPU census resolves CB *signatures*, not kernels. But each signature has a
known dispatch multiset, so a SPLIT=1 per-kernel delta vector predicts a
per-signature delta vector. Two models are compared:

  A ("give-back is real")    every SPLIT=1 per-kernel delta, including the
                             +8.06 us/step charged to laguna_gate_sp_h64_v1.
  B ("give-back is an S1     the same vector with the untouched-kernel deltas
     instrument artefact")    zeroed, keeping only the two edited kernels.

Each model is scored against the observed per-signature deltas with the
per-duplex SD as the error scale. A free-coefficient fit for the h64 attention
bundle is also reported: laguna_sliding_fused_attn_ring_v1, gate_sp_h64_v1 and
oproj_act_h64_v1 occupy identical columns of the design matrix (30 dispatches
per step, always co-resident), so only their sum is identified in situ. That
sum is exactly what separates the two models.
"""
import argparse
import collections
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maple_pr443_duplex_stats import PCT_PER_US_STEP, t95  # noqa: E402
from maple_pr443_step_decomposition import parse_gpuprof_line, shorten  # noqa: E402
from maple_r85_arm_stats import SLOT_RE, select_duplexes  # noqa: E402

TOUCHED = ("sliding_fused_attn_ring", "full_fused_attn_grow")
# Collinear with sliding_fused_attn_ring across every signature.
H64_BUNDLE = ("sliding_fused_attn_ring", "gate_sp_h64", "oproj_act_h64")


def census(path, cbs_per_step, steady_steps):
    recs = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("GPUPROF "):
                rec = parse_gpuprof_line(line)
                if rec is not None:
                    recs.append(rec)
    want = cbs_per_step * steady_steps
    if len(recs) < want:
        raise SystemExit(f"{path}: {len(recs)} records, need {want}")
    dur = collections.Counter()
    cbs = collections.Counter()
    for start, end, nops, names in recs[-want:]:
        key = "|".join(shorten(p) for p in names.split("|"))
        if nops > 1:
            key = f"[{nops}] {key}"
        dur[key] += (end - start) * 1e6
        cbs[key] += 1
    return ({k: v / steady_steps for k, v in dur.items()},
            {k: v / steady_steps for k, v in cbs.items()})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--cbs-per-step", type=int, required=True)
    ap.add_argument("--arms", nargs=2, required=True)
    ap.add_argument("--offset", type=int, default=0, choices=(0, 1))
    ap.add_argument("--s1-json", required=True,
                    help="maple_r85_arm_stats --json-out for the SPLIT=1 set")
    ap.add_argument("--s1-metric", default="adj_us_step",
                    choices=("adj_us_step", "abs_us_step"))
    ap.add_argument("--json-out")
    args = ap.parse_args()
    steady = args.steps - 1
    base_arm, cand_arm = args.arms

    runs = []
    for path in args.paths:
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            raise SystemExit(f"cannot parse slot from {path}")
        dur, cbs = census(path, args.cbs_per_step, steady)
        runs.append(dict(slot=int(m.group(1)), arm=m.group(3), dur=dur, cbs=cbs,
                         set=os.path.basename(os.path.dirname(path))))
    runs.sort(key=lambda r: (r["set"], r["slot"]))
    duplexes = select_duplexes(runs, base_arm, cand_arm, args.offset)
    if len(duplexes) < 2:
        raise SystemExit(f"only {len(duplexes)} duplex(es)")

    sigs = sorted(set.intersection(*[set(r["dur"]) for r in runs]),
                  key=lambda k: -runs[0]["dur"][k])
    cbs = {s: runs[0]["cbs"][s] for s in sigs}

    # SPLIT=1 per-kernel deltas -> per-dispatch rates.
    s1 = json.load(open(args.s1_json))["labels"]
    disp = collections.Counter()
    for s in sigs:
        for part in s.split("] ")[-1].split("|"):
            disp[part] += cbs[s]
    rate = {}
    for kernel, row in s1.items():
        if disp.get(kernel, 0) > 0:
            rate[kernel] = row[args.s1_metric] / disp[kernel]

    def predict(sig, keep):
        out = 0.0
        for part in sig.split("] ")[-1].split("|"):
            if part in rate and keep(part):
                out += rate[part] * cbs[sig]
        return out

    all_k = lambda p: True                                    # noqa: E731
    touched_only = lambda p: any(t in p for t in TOUCHED)      # noqa: E731

    base_slots = [i if runs[i]["arm"] == base_arm else i + 1 for i, _ in duplexes]
    rows = []
    for s in sigs:
        base_us = statistics.mean([runs[j]["dur"][s] for j in base_slots])
        vals = [sign * (math.log(runs[i + 1]["dur"][s]) - math.log(runs[i]["dur"][s]))
                for i, sign in duplexes]
        mean = statistics.mean(vals)
        sd = statistics.stdev(vals)
        hw = t95(len(vals) - 1) * sd / math.sqrt(len(vals))
        rows.append(dict(sig=s, base_us=base_us, cbs=cbs[s],
                         obs=base_us * math.expm1(mean),
                         obs_hw=base_us * hw, obs_sd=base_us * sd,
                         pred_a=predict(s, all_k), pred_b=predict(s, touched_only),
                         h64=cbs[s] * s.count("sliding_fused_attn_ring")))

    print(f"NAT model comparison   arms={base_arm}->{cand_arm}   "
          f"n_duplex={len(duplexes)}   s1_metric={args.s1_metric}")
    print(f"{'us/step':>8} {'cb/st':>5} {'h64':>5} {'obs':>7} {'+-':>6} "
          f"{'predA':>7} {'predB':>7} {'resA':>6} {'resB':>6}  signature")
    chi = {"a": 0.0, "b": 0.0}
    tot = collections.Counter()
    for r in rows:
        se = r["obs_hw"] / t95(len(duplexes) - 1)
        za = (r["obs"] - r["pred_a"]) / se if se else 0.0
        zb = (r["obs"] - r["pred_b"]) / se if se else 0.0
        chi["a"] += za * za
        chi["b"] += zb * zb
        for k in ("obs", "pred_a", "pred_b"):
            tot[k] += r[k]
        print(f"{r['base_us']:8.1f} {r['cbs']:5.1f} {r['h64']:5.0f} "
              f"{r['obs']:+7.2f} {r['obs_hw']:6.2f} {r['pred_a']:+7.2f} "
              f"{r['pred_b']:+7.2f} {za:+6.2f} {zb:+6.2f}  "
              f"{r['sig'][:64]}")
    print(f"\ntotals: obs {tot['obs']:+.2f}  predA(give-back real) "
          f"{tot['pred_a']:+.2f}  predB(give-back is S1 artefact) "
          f"{tot['pred_b']:+.2f} us/step")
    print(f"chi2 over {len(rows)} signatures: A {chi['a']:.1f}  B {chi['b']:.1f}"
          f"   (lower is the better model)")

    # Free coefficient for the identified h64 bundle, per duplex, with the
    # model-B prediction for every other kernel held fixed.
    coefs = []
    for d in range(len(duplexes)):
        num = den = 0.0
        for r in rows:
            if not r["h64"]:
                continue
            vals = [sign * (math.log(runs[i + 1]["dur"][r["sig"]])
                            - math.log(runs[i]["dur"][r["sig"]]))
                    for i, sign in duplexes]
            y = r["base_us"] * math.expm1(vals[d])
            other = predict(r["sig"], lambda p: not any(h in p for h in H64_BUNDLE))
            num += r["h64"] * (y - other)
            den += r["h64"] * r["h64"]
        coefs.append(num / den)
    m = statistics.mean(coefs)
    hw = t95(len(coefs) - 1) * statistics.stdev(coefs) / math.sqrt(len(coefs))
    n_h64 = disp["sliding_fused_attn_ring_v1"]
    with_gb = sum(rate[k] for k in rate if any(h in k for h in H64_BUNDLE))
    no_gb = sum(rate[k] for k in rate
                if any(h in k for h in H64_BUNDLE) and "gate_sp_h64" not in k)
    print(f"\nh64 bundle (sliding+gate_sp_h64+oproj_h64, {n_h64:.0f} dispatches/step)")
    print(f"  in-situ fit        {m*n_h64:+.2f} us/step "
          f"[{(m-hw)*n_h64:+.2f}, {(m+hw)*n_h64:+.2f}]")
    print(f"  SPLIT=1 with give-back    {with_gb*n_h64:+.2f} us/step")
    print(f"  SPLIT=1 give-back removed {no_gb*n_h64:+.2f} us/step")


    if args.json_out:
        out = dict(n_duplex=len(duplexes), s1_metric=args.s1_metric,
                   chi2_model_a=chi["a"], chi2_model_b=chi["b"],
                   total_obs=tot["obs"], total_pred_a=tot["pred_a"],
                   total_pred_b=tot["pred_b"],
                   h64_dispatches=n_h64,
                   h64_fit_us_step=m * n_h64,
                   h64_fit_ci=[(m - hw) * n_h64, (m + hw) * n_h64],
                   h64_pred_with_giveback=with_gb * n_h64,
                   h64_pred_no_giveback=no_gb * n_h64,
                   score_pct_per_us_step=PCT_PER_US_STEP,
                   signatures=[{k: r[k] for k in
                                ("sig", "base_us", "cbs", "h64", "obs",
                                 "obs_hw", "obs_sd", "pred_a", "pred_b")}
                               for r in rows])
        with open(args.json_out, "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
