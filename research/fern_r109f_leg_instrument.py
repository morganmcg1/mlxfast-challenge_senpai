#!/usr/bin/env python3
"""fern_r109f_leg_instrument.py -- adjudicate arms on the LEGS, not the score.

Every ranked receipt reports four timings, not one number:

    officialMetrics.decode_seconds_per_token            candidate decode leg
    officialMetrics.prefill_seconds_per_token           candidate prefill leg
    officialMetrics.baseline_decode_seconds_per_token   reference decode leg
    officialMetrics.baseline_prefill_seconds_per_token  reference prefill leg

The published score is a ratio built from all four, so it inherits the noise of
all four -- and the reference prefill leg is by far the noisiest thing on the
host (cv ~2.0-2.6 %).  Weighted into the score at 0.25 that single leg accounts
for most of the published variance, which is why the leaderboard behaves like a
lottery.

But an *arm* does not have to be adjudicated on the published score.  An arm
changes the candidate, so it can be adjudicated on the candidate leg it targets,
and the candidate legs are much quieter than the composite.  This script
estimates the per-leg instrument noise two independent ways:

  1. identical-executable replay groups -- receipts whose executable is identical
     (comment-only nonce apart).  Code variance is exactly zero, so within-group
     variance is pure instrument.  In this campaign that is the base pair t1/t2
     (k=2) and the atlas-v3 group t4/t5/t6 (k=3), pooled to 3 degrees of freedom.
     Nothing else in the whole 1829-row dataset is replayed: every submission
     gets a fresh package commit, so there are no repeated submissionCommitSha
     values anywhere and these five receipts are the only gauge that exists.

  2. within-solver clustering -- for each prolific solver, the spread of the
     candidate legs across their recent receipts.  This is an *upper* bound on
     instrument noise (their code changes between submissions too), so a small
     upper bound is informative and a large one is not.

and then reports how many receipts per arm each leg needs to resolve a given
effect, next to the same figure for the published score.

Usage:  python3 research/fern_r109f_leg_instrument.py [cache.json] [--since 2026-08-10T00]
"""

from __future__ import annotations

import json
import statistics as st
import sys

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626

LEGS = {
    "candidate decode ": "decode_seconds_per_token",
    "candidate prefill": "prefill_seconds_per_token",
    "reference decode ": "baseline_decode_seconds_per_token",
    "reference prefill": "baseline_prefill_seconds_per_token",
}

# identical-executable replay GROUPS from this campaign (id prefixes).  Every
# member of a group is the same compiled executable, differing only in a
# comment-only receipt nonce, so within-group variance is pure instrument.
REPLAY_GROUPS = [
    ("base t1/t2", ["c1c0ba2c", "88584270"]),
    ("atlasv3 t4/t5/t6", ["ed40f3ee", "0531544b", "cb4de9e0"]),
]


def full_leg(r: dict) -> bool:
    m = r.get("officialMetrics") or {}
    return (
        all(m.get(k) for k in LEGS.values())
        and bool(m.get("passed_correctness"))
        and bool(r.get("officialScore"))
    )


def normalized(m: dict) -> float:
    return (REF_D / m["decode_seconds_per_token"]) ** 0.75 * (
        REF_P / m["prefill_seconds_per_token"]
    ) ** 0.25


def main() -> None:
    cache = "/tmp/subs_p8.json"
    since = "2026-08-10T00"
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--since":
            since = args[i + 1]
        elif not a.startswith("--"):
            cache = a

    rows = [r for r in json.load(open(cache))["submissions"] if full_leg(r)]
    win = [r for r in rows if r["createdAt"] >= since]
    print("=" * 92)
    print("fern R109-F: per-leg instrument resolution")
    print(f"  cache {cache}   full-leg correct {len(rows)}   window >= {since}: {len(win)}")
    print("=" * 92)

    # ---------- 1. paired replays -----------------------------------------
    print("\n1. identical-executable replay groups (zero code variance)")
    print("   within-group cv is pure instrument; groups are pooled by degrees of freedom")
    by_id = {r["id"][:8]: r for r in rows}

    def axis_value(r: dict, name: str, key: str | None) -> float:
        if key is not None:
            return r["officialMetrics"][key]
        return r["officialScore"] if "published" in name else normalized(r["officialMetrics"])

    pair_sd: dict[str, float] = {}
    rows_out = []
    for name, key in list(LEGS.items()) + [("published score ", None), ("normalized       ", None)]:
        cells, ss, df = [], 0.0, 0
        for _, ids in REPLAY_GROUPS:
            got = [by_id[i] for i in ids if i in by_id]
            if len(got) < 2:
                cells.append(float("nan"))
                continue
            vals = [axis_value(r, name, key) for r in got]
            cv = 100.0 * st.stdev(vals) / st.fmean(vals)
            cells.append(cv)
            ss += (len(vals) - 1) * cv * cv
            df += len(vals) - 1
        if df == 0:
            continue
        sd = (ss / df) ** 0.5
        pair_sd[name.strip()] = sd
        rows_out.append((name, cells, sd))
    hdr = "".join(f"{g[0]+' (k=%d)'%len(g[1]):>22}" for g in REPLAY_GROUPS)
    print(f"  {'axis':<18}{hdr}{'pooled sd':>12}")
    for name, cells, sd in rows_out:
        body = "".join(f"{c:21.4f}%" for c in cells)
        print(f"  {name:<18}{body}{sd:11.4f}%")

    # ---------- 2. field spread of each leg in the window ------------------
    print(f"\n2. field spread of each leg in the window (n={len(win)}), and the code residual")
    print("   robust cv = 1.4826 * MAD / median: a single wild arm (one solver shipped a")
    print("   3.6 %-cv decode regression in this window) inflates the plain cv, so the")
    print("   robust column is the honest estimate of how much the *typical* package differs.")
    print(f"  {'axis':<18}{'median':>14}{'cv':>10}{'robust cv':>11}{'instrument':>12}"
          f"{'code resid':>12}  note")
    for name, key in LEGS.items():
        vals = [r["officialMetrics"][key] for r in win]
        mean = st.fmean(vals)
        med = st.median(vals)
        cv = 100.0 * st.stdev(vals) / mean
        mad = st.median([abs(v - med) for v in vals])
        rcv = 100.0 * 1.4826 * mad / med
        inst = pair_sd.get(name.strip(), 0.0)
        v = rcv * rcv - inst * inst
        resid = f"{(v ** 0.5):9.4f}%" if v > 0 else "     ---  "
        note = "" if v > 0 else "noise >= spread"
        print(f"  {name:<18}{med*1e6:13.4f}us{cv:9.4f}%{rcv:10.4f}%{inst:11.4f}%"
              f"{resid:>12}  {note}")
    print("\n   ESTIMATOR WARNING, and a self-correction.  Which leg is the bigger *code*")
    print("   lever depends on the estimator, and the two answers disagree:")
    print("     plain cv : decode 0.75 x 0.224 = 0.168 %  vs  prefill 0.25 x 0.678 = 0.169 %")
    print("     robust cv: decode 0.75 x 0.224 = 0.168 %  vs  prefill 0.25 x 0.158 = 0.040 %")
    print("   The plain candidate-prefill cv is inflated by a handful of prefill blow-ups")
    print("   (our own QHOIST receipt sat at 196.30 us against a 188 us population), so the")
    print("   robust column is the one to believe: DECODE is the bigger code lever, by ~4x.")
    print("   I had drafted the opposite claim from the plain cv before running this; it is")
    print("   withdrawn here.  What survives estimator choice is the *instrument* column:")
    print("   candidate prefill is the quietest axis on the host (0.075 %) and therefore the")
    print("   cheapest place to adjudicate an arm, whatever the size of the field's spread.")

    # ---------- 3. within-solver spread of the candidate legs --------------
    print("\n3. within-solver spread of the candidate legs in the window (upper bound on noise)")
    bysolver: dict[str, list[dict]] = {}
    for r in win:
        bysolver.setdefault(r["solverUsername"], []).append(r)
    print(f"  {'solver':<20}{'n':>3}{'cand decode cv':>16}{'cand prefill cv':>17}")
    for s, rs in sorted(bysolver.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < 3:
            continue
        d = [r["officialMetrics"]["decode_seconds_per_token"] for r in rs]
        p = [r["officialMetrics"]["prefill_seconds_per_token"] for r in rs]
        print(
            f"  {s:<20}{len(rs):3d}{100*st.stdev(d)/st.fmean(d):15.4f}%{100*st.stdev(p)/st.fmean(p):16.4f}%"
        )

    # ---------- 4. receipts per arm --------------------------------------
    print("\n4. receipts per arm to resolve an effect (2-sample, alpha .05, power .95)")
    print("   n = 2 (1.960 + 1.645)^2 (sd/delta)^2 = 26.0 (sd/delta)^2")
    print(f"  {'effect on the leg':<20}" + "".join(f"{k:>20}" for k in pair_sd))
    for eff in (0.10, 0.20, 0.30, 0.50, 1.00):
        cells = ""
        for k, sd in pair_sd.items():
            n = 26.0 * (sd / eff) ** 2
            cells += f"{max(1, round(n)):19d} "
        print(f"  {eff:.2f}% {'':13}{cells}")
    print(
        "\n  Read: an arm that moves the candidate prefill leg by 0.30 % is a 2-receipt\n"
        "  measurement on that leg, and a ~77-receipt measurement on the published score.\n"
        "  The arm did not become easier; the instrument was being read in the wrong place."
    )

    # ---------- 5. class comparison, with the plausibility guard -----------
    print("\n5. our own class comparison on the normalized axis, with the plausibility guard")
    classes = {
        "r109F-base": ["c1c0ba2c", "88584270"],
        "r109F-atlasv3": ["ed40f3ee", "0531544b", "cb4de9e0"],
    }
    means, ns = {}, {}
    for k, ids in classes.items():
        got = [by_id[i] for i in ids if i in by_id]
        if not got:
            continue
        vals = [normalized(r["officialMetrics"]) for r in got]
        means[k], ns[k] = st.fmean(vals), len(vals)
        print(f"   {k:<16} n {len(vals)}  mean normalized {means[k]:.6f}")
    if len(means) == 2:
        inst = pair_sd["normalized"]
        a, b = "r109F-atlasv3", "r109F-base"
        eff = 100.0 * (means[a] - means[b]) / means[b]
        se = inst * (1 / ns[a] + 1 / ns[b]) ** 0.5
        print(f"   {a} - {b} = {eff:+.4f} %   instrument sd {inst:.4f} %"
              f"   se {se:.4f} %  =>  {eff/se:.2f} sigma")
        # the guard: is an effect this big even possible for a field package?
        d_key = "candidate decode"
        dvals = [r["officialMetrics"][LEGS[d_key + " "]] for r in win]
        dmed = st.median(dvals)
        dmad = st.median([abs(v - dmed) for v in dvals])
        drcv = 100.0 * 1.4826 * dmad / dmed
        dcode = max(0.0, drcv ** 2 - pair_sd[d_key] ** 2) ** 0.5
        print("\n   PLAUSIBILITY GUARD.  Two independent measurements of how much code can")
        print("   possibly move this score disagree with the point estimate above:")
        print(f"     - decode-leg code differentiation across the whole field: {dcode:.4f} %")
        print(f"       (robust cv {drcv:.4f} % minus instrument {pair_sd[d_key]:.4f} %), which at")
        print(f"       the 0.75 decode weight caps a decode-only arm at {0.75*dcode:.4f} % of score;")
        print("     - our own local A/B of exactly this arm measured -0.0260 % decode")
        print("       (= +0.0166 % score), and local noise is ~0.35 %, so it saw nothing.")
        print(f"   A {eff:+.4f} % code effect from one threadgroup-size constant is therefore")
        print("   larger than the entire field's decode code spread.  The honest reading is")
        print("   that the 1.8 sigma is a fluctuation of a k=3-vs-k=2 comparison, not a win;")
        print("   the base group's absurd 0.0014 % internal agreement (the very sample that")
        print("   produced this campaign's retracted claim #1) is what makes se look small.")
        print("   Ship atlas v3 because it is not worse and is cheap, not because of this.")


if __name__ == "__main__":
    main()
