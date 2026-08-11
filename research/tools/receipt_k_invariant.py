#!/usr/bin/env python3
"""Audit any receipt triple, and re-price the decision-axis noise.

Run:  python3 research/tools/receipt_k_invariant.py      (no arguments, read-only)

WHY THIS EXISTS. Two numbers get called "the score" and they are not the same
number. `cs` (candidateScore) is computed against a FIXED reference baseline;
`officialScore` -- what the leaderboard ranks, what the accept/reject gate reads
-- is computed against a baseline RE-MEASURED in the same session as your
candidate. The identity is already in the record at
`research/CURRENT_RESEARCH_STATE.md` (the n=84 reconstruction):

    officialScore = (baseline_decode / dec)^0.75 * (baseline_prefill / pre)^0.25
    cs            = (MB_D          / dec)^0.75 * (MB_P            / pre)^0.25
    MB_D = 0.013855009542 s/tok     MB_P = 0.000372473193 s/tok

This tool does three things with it.

  1. Restates the cs identity in its portable audit form. With the candidate's
     own legs in microseconds, cs * D^0.75 * P^0.25 is a CONSTANT, K. Any
     receipt that reports (cs, decode, prefill) can be checked in one line
     with no API call and no baseline. A triple that misses K is mislabelled,
     mistranscribed, or stitched from two different measurement payloads.
     It has already caught one mislabelled column (an amendment table headed
     "base decode / base prefill" that K proves holds CANDIDATE legs).

  2. Measures the noise on BOTH axes over the identical-program replicate
     groups, and shows the leaderboard-facing axis is the wider one in every
     group. A sigma measured on `cs` is a lower rail BY CONSTRUCTION -- the K
     identity says `cs` cannot contain baseline information at all -- so it must
     never be quoted as the sigma that decides a fire.

  3. Reprices P(one draw >= bar) across the sigma choices that have been
     published for it, because that probability is dominated by which sigma you
     pick rather than by data. That instability is the finding; the number is
     not. Carry the model-free bound in the brief, not any row of this table.

Nothing here touches the submission channel or the network.
"""
from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "research" / "artifacts" / "advisor-r103" / "replicate-sigma.json"
CORPUS = ROOT / "research" / "data" / "official_submission_corpus_2026-08-11T1152Z.tsv"

MB_D_S = 0.013855009542      # fixed reference decode, s/token
MB_P_S = 0.000372473193      # fixed reference prefill, s/token
K = (MB_D_S * 1e6) ** 0.75 * (MB_P_S * 1e6) ** 0.25   # legs in microseconds

BAR = 2.6195531094824        # final leaderboard bar, verified at close
NULL_GROUP = "dc437b0e"      # the 5 identical-program ranked null replicates

# The one replicate group whose CANDIDATE legs are not replicates of each other:
# one draw at 222.37 us/tok prefill against 192.8-206.5 for its three siblings,
# a 15.3 % span where every other group spans <= 1.3 %. Excluded from pooling and
# printed anyway, because hiding an outlier is how a sigma gets published twice.
OUTLIER_GROUP = "7cbffc2c"

# Winning-path receipt named in the 08-11 operator bulletin. Only three of its
# numbers were published; K supplies the fourth.
BULLETIN = {
    "receipt": "5fae2f13-577e-462d-afce-60a97d25bba6",
    "official": 2.575215,
    "D": 4914.778,      # us/step  (4.914778 ms/token)
    "P": 188.321,       # us/token
}


def cs_from_legs(decode_us: float, prefill_us: float) -> float:
    """The candidate score implied by a candidate's own two legs."""
    return K / (decode_us ** 0.75 * prefill_us ** 0.25)


def load():
    art, groups = {}, {}
    if ARTIFACT.exists():
        blob = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        for g in blob.get("groups", []):
            for r in g.get("receipts", []):
                if r.get("cs") and r.get("D") and r.get("P"):
                    art[r["id8"][:7]] = r
                    groups.setdefault(g["digest"][:8], []).append(r["id8"][:7])
    listing = {}
    if CORPUS.exists():
        for line in CORPUS.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                continue
            f = line.split("\t")
            if len(f) >= 3:
                try:
                    listing[f[0][:7]] = float(f[2])
                except ValueError:
                    pass
    return art, groups, listing


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if not da or not db:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)


def phi(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def main() -> int:
    art, groups, listing = load()
    print("K = MB_D^0.75 * MB_P^0.25 (legs in us) = %.6f" % K)
    if not art:
        print("artifact %s absent in this checkout; identity above still stands." % ARTIFACT.name)
        return 0

    # --- 1. the audit ------------------------------------------------------
    resid = [(abs(cs_from_legs(r["D"], r["P"]) / r["cs"] - 1), k) for k, r in art.items()]
    worst, who = max(resid)
    print("\n1. AUDIT  cs == K / (D^0.75 * P^0.25)")
    print("   receipts with all three fields: %d, spanning cs %.6f .. %.6f"
          % (len(art), min(r["cs"] for r in art.values()), max(r["cs"] for r in art.values())))
    print("   worst relative residual: %.3e  (%s)  -> float-exact" % (worst, who))
    print("   use: any (cs, decode us/step, prefill us/tok) triple that misses K by more")
    print("        than ~1e-9 is not one measurement. Solve for whichever leg is suspect.")

    # --- 2. the two axes ---------------------------------------------------
    fac = {k: math.log(listing[k] / art[k]["cs"]) for k in art if k in listing}
    print("\n2. NOISE, BOTH AXES, within identical-program replicate groups")
    print("   n matched to an officialScore: %d of %d" % (len(fac), len(art)))
    print("   %-10s %-3s %-9s %-9s %-9s %-9s %-7s"
          % ("group", "n", "sd lnD%", "sd lnP%", "sd lncs%", "sd f%", "sd lnOff%"))
    rows, wider = [], 0
    for g in sorted(groups):
        ids = [i for i in groups[g] if i in fac]
        if len(ids) < 3:
            continue
        D = [math.log(art[i]["D"]) for i in ids]
        P = [math.log(art[i]["P"]) for i in ids]
        cs = [math.log(art[i]["cs"]) for i in ids]
        ff = [fac[i] for i in ids]
        off = [math.log(listing[i]) for i in ids]
        print("   %-10s %-3d %-9.4f %-9.4f %-9.4f %-9.4f %-7.4f%s"
              % (g, len(ids), 100 * st.stdev(D), 100 * st.stdev(P), 100 * st.stdev(cs),
                 100 * st.stdev(ff), 100 * st.stdev(off),
                 "   <- candidate legs are not replicates; excluded from pooling"
                 if g == OUTLIER_GROUP else ""))
        wider += st.stdev(off) > st.stdev(cs)
        if g != OUTLIER_GROUP:
            rows.append((len(ids), st.stdev(cs), st.stdev(ff), st.stdev(off),
                         [x - st.mean(cs) for x in cs], [x - st.mean(ff) for x in ff]))
    ngrp = sum(1 for g in groups if len([i for i in groups[g] if i in fac]) >= 3)
    print("   sd(ln officialScore) > sd(ln cs) in %d of %d groups"
          " (one-sided sign test p = %.3f)" % (wider, ngrp, 0.5 ** ngrp))

    df = sum(n - 1 for n, *_ in rows)

    def pooled(j):
        return math.sqrt(sum((n - 1) * t[j - 1] ** 2 for n, *t in rows) / df)

    s_cs, s_f, s_off = pooled(1), pooled(2), pooled(3)
    rr = corr([x for r in rows for x in r[4]], [x for r in rows for x in r[5]])
    print("   pooled over %d clean groups, df %d:" % (len(rows), df))
    print("     sd(ln cs)             = %.4f %%   candidate term only -- LOWER RAIL BY CONSTRUCTION"
          % (100 * s_cs))
    print("     sd(session factor f)  = %.4f %%   baseline arm" % (100 * s_f))
    print("     sd(ln officialScore)  = %.4f %%   THE AXIS ACCEPTANCE READS" % (100 * s_off))
    print("     corr(ln cs, f)        = %+.3f     (n=84 corpus estimate on record: -0.126)" % rr)
    print("     independence quadrature would give %.4f %%" % (100 * math.hypot(s_cs, s_f)))
    lo = s_off * math.sqrt(df / 23.337)      # chi2 0.975/0.025, df 12
    hi = s_off * math.sqrt(df / 4.404)
    print("     95 %% interval on sd(ln officialScore): [%.4f %%, %.4f %%]" % (100 * lo, 100 * hi))

    # --- 3. what that does to the tail ------------------------------------
    print("\n3. P(one draw >= bar %.13f) for a program centred at 2.586989" % BAR)
    need = math.log(BAR / 2.586989)
    print("   required move = %+.4f %% in log units" % (100 * need))
    print("   %-44s %-10s %-8s %s" % ("sigma, and where it came from", "sigma %", "z", "P"))
    for name, s in (("brief 6.5-corrected: df 4, one group", 0.003728),
                    ("this tool: direct, df %d" % df, s_off),
                    ("independence quadrature, n=84 legs", math.hypot(0.002494, 0.005352)),
                    ("low end of the df-%d interval" % df, lo),
                    ("high end of the df-%d interval" % df, hi)):
        print("   %-44s %-10.4f %-8.3f %.3f %%" % (name, 100 * s, need / s, 100 * phi(need / s)))
    print("   spread across sigma choices: %.0fx. The instability IS the result." % (
        phi(need / hi) / phi(need / 0.003728)))
    print("   Do not carry any row of this table into a decision. Carry the model-free bound.")

    # --- 4. the bulletin receipt ------------------------------------------
    b = BULLETIN
    cs_b = cs_from_legs(b["D"], b["P"])
    f_b = math.log(b["official"] / cs_b)
    print("\n4. RECOVERING THE FOURTH NUMBER  (receipt %s)" % b["receipt"][:8])
    print("   published: officialScore %.6f, decode %.3f us/step, prefill %.3f us/tok"
          % (b["official"], b["D"], b["P"]))
    print("   K-implied cs           = %.6f" % cs_b)
    print("   session factor f       = %+.4f %%   (an unlucky baseline arm, not a slow candidate)"
          % (100 * f_b))
    ids = [i for i in groups.get(NULL_GROUP, []) if i in art]
    if len(ids) >= 3:
        m = st.mean([math.log(art[i]["cs"]) for i in ids])
        s = st.stdev([math.log(art[i]["cs"]) for i in ids])
        print("   vs the %d identical-program nulls in group %s (mean cs %.6f, sd %.4f %%):"
              % (len(ids), NULL_GROUP, math.exp(m), 100 * s))
        print("     z on the cs axis = %+.2f sigma -> indistinguishable from a null draw"
              % ((math.log(cs_b) - m) / s))
    print("   distance to the bar    = %.4f %% in log units, %.2f sigma on the official axis"
          % (100 * math.log(BAR / b["official"]), math.log(BAR / b["official"]) / s_off))
    print("\n   Honest alternative reading: the f above assumes all three published numbers")
    print("   came from one measurement payload. If instead the score IS the candidate score,")
    print("   exactly one of the three has to move to restore K -- score %.6f, or decode" % cs_b)
    print("   %.3f us/step, or prefill %.3f us/tok. Which one cannot be settled from here."
          % (K ** (4 / 3) / b["official"] ** (4 / 3) / b["P"] ** (1 / 3),
             (K / (b["official"] * b["D"] ** 0.75)) ** 4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
