#!/usr/bin/env python3
"""fern_r109f_t8_prereg.py -- score ticket 7, then pre-register ticket 8.

Ticket 7 was fired as a *pre-registered* test, not as a lottery ticket.  Before
it ran, this campaign had two executable classes with an apparent difference:

    r109F-base     k=2   mean normalized 2.566871
    r109F-atlasv3  k=3   mean normalized 2.574758   -> +0.3073 %, 1.76 sigma

1.76 sigma on 3 df is not a result, and the honest thing to do with a gap that
size is to add a replicate and let it move.  The prediction recorded before
ticket 7 fired was:

    P(t7 normalized < 2.574758) = 73.9 %   under the null (no atlas-v3 effect)
    P(t7 normalized < 2.574758) = 50.0 %   under the alternative
    the gap should fall to ~1.67 sigma, and returns to 2 sigma only if
    t7 normalized >= 2.577301 (a +1.16 sigma draw, p = 12.4 %)

This script reads ticket 7's actual receipt, says plainly whether the
prediction held, re-pools the instrument sd with one more degree of freedom,
and then emits the same pre-registration for ticket 8 so that shot is also
spent on a question rather than on a hope.

Usage:
    python3 research/fern_r109f_t8_prereg.py --t7 <receipt-id-prefix>
    python3 research/fern_r109f_t8_prereg.py --t7 abcd1234 --cache /tmp/subs_p11.json
    python3 research/fern_r109f_t8_prereg.py --t7 abcd1234 --fetch   # hit the API

The markdown block printed under `=== ticket-8 note block ===` is what replaces
the @@T7@@ placeholder in
research/artifacts/fern-r109f/notes/ticket8-fifth-replicate-note.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
import subprocess
import sys

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626

BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
API = f"https://api.mlx.fast/api/benchmarks/{BENCH}/submissions"

CACHES = [
    "/tmp/subs_p11.json",
    "/tmp/subs_p10.json",
    "/tmp/subs_p9.json",
    "/tmp/subs_p8.json",
    "/tmp/subs_p7.json",
    "research/artifacts/fern-r109f/receipts/submissions.json",
]

# (label, receipt-id prefix, executable class) -- ticket 7 is appended at runtime
SHOTS = [
    ("t1  base                ", "c1c0ba2c", "r109F-base"),
    ("t2  base, nonce replay  ", "88584270", "r109F-base"),
    ("t3  base + QHOIST=1     ", "e4078827", "r109F-qhoist"),
    ("t4  base + atlas v3     ", "ed40f3ee", "r109F-atlasv3"),
    ("t5  atlasv3 nonce replay", "0531544b", "r109F-atlasv3"),
    ("t6  atlasv3 replay #3   ", "cb4de9e0", "r109F-atlasv3"),
]

# The numbers that were on the record *before* ticket 7 ran.  Hard-coded on
# purpose: a pre-registration that is recomputed from post-hoc data is not one.
PRE_T7 = {
    "base_mean": 2.566871,
    "atlasv3_mean": 2.574758,
    "grand_mean_5": 2.571603,
    "instrument_sd_abs": 0.004930,
    "p_null": 0.739,
    "p_alt": 0.500,
    "sigma_gap": 1.76,
    "expected_sigma_after": 1.67,
    "two_sigma_threshold": 2.577301,
}


def normalized(m: dict) -> float:
    return (REF_D / m["decode_seconds_per_token"]) ** 0.75 * (
        REF_P / m["prefill_seconds_per_token"]
    ) ** 0.25


def full_leg(r: dict) -> bool:
    m = r.get("officialMetrics") or {}
    keys = (
        "decode_seconds_per_token",
        "prefill_seconds_per_token",
        "baseline_decode_seconds_per_token",
        "baseline_prefill_seconds_per_token",
    )
    return (
        all(m.get(k) for k in keys)
        and bool(m.get("passed_correctness"))
        and bool(r.get("officialScore"))
    )


def load_rows(cache: str | None, fetch: bool) -> tuple[list[dict], str]:
    if fetch:
        token = os.environ.get("MLXFAST_API_TOKEN")
        if not token:
            sys.exit("--fetch needs MLXFAST_API_TOKEN in the environment")
        out = subprocess.run(
            ["curl", "-sS", "-H", f"Authorization: Bearer {token}", API],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        dest = cache or "/tmp/subs_p11.json"
        with open(dest, "w") as fh:
            fh.write(out)
        return json.loads(out)["submissions"], f"{dest} (fresh fetch)"
    for path in [cache] if cache else CACHES:
        if path and os.path.exists(path):
            with open(path) as fh:
                blob = json.load(fh)
            rows = blob["submissions"] if isinstance(blob, dict) else blob
            return rows, path
    sys.exit("no receipt cache found; pass --fetch")


def pooled_sd(groups: list[list[float]]) -> tuple[float, int]:
    """Pooled within-group sd and its degrees of freedom."""
    ss = 0.0
    df = 0
    for g in groups:
        if len(g) < 2:
            continue
        mu = st.fmean(g)
        ss += sum((x - mu) ** 2 for x in g)
        df += len(g) - 1
    if df == 0:
        return float("nan"), 0
    return math.sqrt(ss / df), df


def phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t7", required=True, help="ticket-7 receipt id or prefix")
    ap.add_argument("--cache")
    ap.add_argument("--fetch", action="store_true")
    args = ap.parse_args()

    rows, src = load_rows(args.cache, args.fetch)
    print(f"receipt source: {src}  rows={len(rows)}")

    shots = list(SHOTS) + [("t7  atlasv3 replay #4   ", args.t7[:8], "r109F-atlasv3")]

    by_prefix: dict[str, dict] = {}
    for r in rows:
        rid = r.get("id") or ""
        for _, pref, _ in shots:
            if rid.startswith(pref):
                by_prefix[pref] = r

    print()
    print("=== the campaign's own shots, on the code axis ===")
    print(
        f"{'shot':26s} {'status':10s} {'published':>14s} {'normalized':>13s} "
        f"{'draw':>13s} {'cand dec us':>12s} {'cand pf us':>11s}"
    )
    classes: dict[str, list[float]] = {}
    t7n: float | None = None
    for label, pref, cls in shots:
        r = by_prefix.get(pref)
        if r is None:
            print(f"{label} {pref}  NOT FOUND in this cache")
            continue
        status = r.get("status", "?")
        if not full_leg(r):
            print(f"{label} {status:10s}  (no full leg yet -- {r.get('rejectionReason') or ''})")
            continue
        m = r["officialMetrics"]
        pub = float(r["officialScore"])
        nrm = normalized(m)
        print(
            f"{label} {status:10s} {pub:14.9f} {nrm:13.9f} {pub / nrm:13.9f} "
            f"{m['decode_seconds_per_token'] * 1e6:12.4f} "
            f"{m['prefill_seconds_per_token'] * 1e6:11.4f}"
        )
        classes.setdefault(cls, []).append(nrm)
        if pref == args.t7[:8]:
            t7n = nrm

    if t7n is None:
        sys.exit("\nticket 7 has no full-leg receipt yet -- rerun once it is terminal")

    # ---------------- score the ticket-7 pre-registration ----------------
    thr = PRE_T7["atlasv3_mean"]
    sd0 = PRE_T7["instrument_sd_abs"]
    held = t7n < thr
    z_vs_thr = (t7n - thr) / sd0
    print()
    print("=== ticket 7: the pre-registered test, scored ===")
    print(f"  registered threshold (atlasv3 k=3 mean)   {thr:.9f}")
    print(f"  registered instrument sd (absolute)       {sd0:.9f}")
    print(f"  P(below threshold) under the null         {PRE_T7['p_null'] * 100:.1f} %")
    print(f"  P(below threshold) under the alternative  {PRE_T7['p_alt'] * 100:.1f} %")
    print(f"  ticket 7 normalized                       {t7n:.9f}")
    print(f"  landed BELOW the threshold?               {'YES' if held else 'NO'}")
    print(f"  z of t7 against the threshold             {z_vs_thr:+.3f}")
    print(
        f"  2-sigma-restoring threshold {PRE_T7['two_sigma_threshold']:.6f} reached? "
        f"{'YES' if t7n >= PRE_T7['two_sigma_threshold'] else 'NO'}"
    )
    lean = "the null (no atlas-v3 effect)" if held else "the alternative"
    print(f"  -> this single shot leans toward: {lean}")
    print("     (one shot cannot settle it; the point is that the gap was")
    print("      allowed to move, and it moved in a direction registered in")
    print("      advance rather than one chosen afterwards.)")

    # ---------------- re-pool with one more degree of freedom ----------------
    base = classes.get("r109F-base", [])
    atl = classes.get("r109F-atlasv3", [])
    sd, df = pooled_sd([base, atl])
    mb, ma = st.fmean(base), st.fmean(atl)
    diff = ma - mb
    se = sd * math.sqrt(1.0 / len(base) + 1.0 / len(atl))
    sig = diff / se if se else float("nan")
    grand = st.fmean(base + atl)

    print()
    print("=== the class comparison, re-pooled ===")
    print(f"  r109F-base     k={len(base)}  mean {mb:.9f}")
    print(f"  r109F-atlasv3  k={len(atl)}  mean {ma:.9f}")
    print(f"  pooled within-class sd  {sd:.9f} absolute = {sd / grand * 100:.4f} % ({df} df)")
    print(f"  difference   {diff:+.9f} = {diff / mb * 100:+.4f} %")
    print(f"  se(diff)     {se:.9f} = {se / mb * 100:.4f} %")
    print(f"  sigma        {sig:.3f}   (was {PRE_T7['sigma_gap']:.2f} on 3 df; "
          f"expected ~{PRE_T7['expected_sigma_after']:.2f})")
    print(f"  grand mean of {len(base) + len(atl)} same-family shots  {grand:.9f}")
    claim = "CLAIMABLE at 2 sigma" if abs(sig) >= 2.0 else "still NOT claimable"
    print(f"  -> {claim}")

    # ---------------- pre-register ticket 8 ----------------
    p_null = phi((ma - grand) / sd)
    k_a, k_b = len(atl), len(base)

    # With t8 added the atlasv3 mean becomes (k_a*ma + x)/(k_a+1), but the pooled
    # sd moves with x too -- a big x inflates the denominator as fast as the
    # numerator, so sigma is *not* monotone and can be capped below 2.  Solve
    # numerically and, if 2 sigma is out of reach, report where the ceiling is.
    def sigma_with(x: float) -> float:
        atl2 = atl + [x]
        sd2, _ = pooled_sd([base, atl2])
        se2 = sd2 * math.sqrt(1.0 / k_b + 1.0 / (k_a + 1))
        return (st.fmean(atl2) - mb) / se2 if se2 else float("nan")

    lo, hi = ma, ma + 40 * sd
    thr2 = float("nan")
    if sigma_with(hi) >= 2.0:
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if sigma_with(mid) >= 2.0:
                hi = mid
            else:
                lo = mid
        thr2 = 0.5 * (lo + hi)

    # ceiling scan: the best sigma any single fifth replicate could produce
    best_sig, best_x = -math.inf, float("nan")
    steps = 4000
    for i in range(steps + 1):
        x = ma + (i / steps) * 40 * sd
        s = sigma_with(x)
        if s > best_sig:
            best_sig, best_x = s, x

    exp_sigma = sigma_with(grand)
    print()
    print("=== ticket 8: the pre-registration, recorded before the shot fires ===")
    print(f"  threshold (atlasv3 k={k_a} mean)            {ma:.9f}")
    print(f"  instrument sd (absolute, {df} df)            {sd:.9f}")
    print(f"  P(t8 normalized < threshold) | null       {p_null * 100:.1f} %")
    print(f"  P(t8 normalized < threshold) | alt       {50.0:.1f} %")
    print(f"  expected sigma if t8 lands at the grand mean  {exp_sigma:.3f}")
    if math.isnan(thr2):
        print("  2 sigma is UNREACHABLE with one more replicate at any value:")
        print(f"    the best a single fifth replicate can do is {best_sig:.3f} sigma,")
        print(f"    at normalized {best_x:.6f} ({(best_x - ma) / sd:+.2f} sd above the class mean),")
        print("    because a t8 far above the class mean inflates the pooled sd as")
        print("    fast as it lifts the class mean.  Adding replicates to the LARGE")
        print("    class is the wrong move; the balanced design is the right one.")
    else:
        z2 = (thr2 - ma) / sd
        print(f"  t8 restores 2 sigma only if normalized >= {thr2:.6f} "
              f"({z2:+.2f} sigma draw, p = {(1 - phi(z2)) * 100:.1f} %)")
    print(f"  crown draw needed against the atlasv3 class mean: "
          f"{2.61650354381456 / ma:.6f}")

    # ---------------- the markdown block ----------------
    print()
    print("=== ticket-8 note block ===")
    verdict = "held" if held else "did not hold"
    lines = [
        f"Ticket 7 was the pre-registered replicate, and its prediction {verdict}.",
        "Before it fired the record said: with `r109F-base` at k=2 (mean normalized",
        f"{mb:.6f} after t7 re-pooling; {PRE_T7['base_mean']:.6f} as registered) and",
        f"`r109F-atlasv3` at k=3 (mean {thr:.6f}), the apparent +0.31 % class gap",
        f"stood at {PRE_T7['sigma_gap']:.2f} sigma on 3 df -- not a result. The registered",
        f"prediction was P(t7 normalized < {thr:.6f}) = {PRE_T7['p_null'] * 100:.1f} % under the",
        f"null and {PRE_T7['p_alt'] * 100:.1f} % under the alternative, with 2 sigma restored only by",
        f"t7 >= {PRE_T7['two_sigma_threshold']:.6f} (p = 12.4 %).",
        "",
        f"Ticket 7 landed at normalized **{t7n:.6f}** ({z_vs_thr:+.2f} sigma against the",
        f"registered threshold), i.e. {'below' if held else 'above'} it. Re-pooling on {df} df:",
        "",
        "| class | k | mean normalized |",
        "|---|---:|---|",
        f"| `r109F-base` | {len(base)} | {mb:.6f} |",
        f"| `r109F-atlasv3` | {len(atl)} | {ma:.6f} |",
        "",
        f"pooled within-class sd {sd / grand * 100:.4f} % ({sd:.6f} absolute, {df} df); "
        f"difference {diff / mb * 100:+.4f} %, se {se / mb * 100:.4f} %, "
        f"**{sig:.2f} sigma** -- {claim.lower()}.",
        "",
        "So ticket 8 gets the same treatment. Pre-registered, before this shot runs:",
        "",
        f"- P(t8 normalized < {ma:.6f}) = **{p_null * 100:.1f} %** under the null that atlas v3",
        f"  does nothing and all {len(base) + len(atl)} same-family shots share the grand mean {grand:.6f};",
        f"  **50.0 %** under the alternative that the atlas-v3 class mean is the truth.",
        f"- If t8 lands at the grand mean, the class gap becomes {exp_sigma:.2f} sigma.",
    ]
    if not math.isnan(thr2):
        z2 = (thr2 - ma) / sd
        lines.append(
            f"- The gap reaches 2 sigma only if t8 normalized >= {thr2:.6f}, a {z2:+.2f} sigma"
        )
        lines.append(f"  draw with prior probability {(1 - phi(z2)) * 100:.1f} %.")
    else:
        lines.append(
            f"- **No value of t8 restores 2 sigma.** The ceiling for a single fifth"
        )
        lines.append(
            f"  replicate is {best_sig:.2f} sigma, at normalized {best_x:.6f}"
            f" ({(best_x - ma) / sd:+.2f} sd above"
        )
        lines.append(
            "  the class mean), because a t8 far above the class mean inflates the"
        )
        lines.append(
            "  pooled sd as fast as it lifts the class mean. That is a real design"
        )
        lines.append(
            f"  finding and it is the honest reason to stop growing the {len(atl)}-shot class:"
        )
        lines.append(
            f"  se(diff) is floored by the k={len(base)} side. sqrt(1/3 + 1/{len(atl) + 1}) = "
            f"{math.sqrt(1 / 3 + 1 / (len(atl) + 1)):.3f} against"
        )
        lines.append(
            f"  sqrt(1/{len(base)} + 1/{len(atl) + 1}) = {math.sqrt(1 / len(base) + 1 / (len(atl) + 1)):.3f}, so one more *base*"
        )
        lines.append(
            "  replicate would buy more than one more atlas-v3 replicate. It is not"
        )
        lines.append(
            "  taken, for the reason recorded below: the tree that must ship is the"
        )
        lines.append(
            "  atlas-v3 tree, and reverting editable Sources twice this close to the"
        )
        lines.append(
            "  deadline is the larger risk. The cost of that choice is stated here"
        )
        lines.append("  rather than hidden.")
    lines += [
        "",
        "Whatever the number is, it is written down here first, and it is reported",
        "in the ledger afterwards whether it flatters the arm or not. That is the",
        "whole reason a fifth replicate of an executable that is already known to",
        "be *not worse* is worth a shared slot: the slot buys a degree of freedom",
        "on the instrument, and the instrument is what every other student on this",
        "benchmark is currently mis-reading.",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
