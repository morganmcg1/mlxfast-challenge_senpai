#!/usr/bin/env python3
"""Measure the two arms of the ranked paired receipt separately.

Question this answers (PR #40 r2 item 4):
  the pinned-code BASELINE arm shows ~1.9% relative sd on prefill while the
  candidate-side spread used for the r1 decision was ~0.18%.  Same axis, same
  machine, 10x apart.  Which arm is actually noisy, do the two arms co-move,
  and is `ns` (a baseline-free content score) a valid cross-session screen?

Usage:
  python3 research/receipt_arm_asymmetry.py /tmp/subs_r2.json

Input is the raw JSON array from
  GET https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions
Read-only; no network access, no repository mutation.
"""

import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

# ---------------------------------------------------------------- helpers


def rel_sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = statistics.fmean(xs)
    return statistics.stdev(xs) / m


def pooled_within_rel_sd(groups):
    """Pooled within-group relative sd.  groups: list of lists of values."""
    ss, dof = 0.0, 0
    for g in groups:
        if len(g) < 2:
            continue
        m = statistics.fmean(g)
        if m == 0:
            continue
        ss += sum((v / m - 1.0) ** 2 for v in g)
        dof += len(g) - 1
    if dof == 0:
        return float("nan"), 0
    return math.sqrt(ss / dof), dof


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(xs, ys):
    return pearson(ranks(xs), ranks(ys))


def corr_ci95(r, n):
    """Fisher z 95% CI for a correlation."""
    if n < 4 or not (-1 < r < 1):
        return float("nan"), float("nan")
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    lo, hi = z - 1.96 * se, z + 1.96 * se
    return math.tanh(lo), math.tanh(hi)


def two_means_1d(xs, iters=200):
    """Minimal 1-D 2-means split; returns (lo_centre, hi_centre, n_lo, n_hi)."""
    lo, hi = min(xs), max(xs)
    c0, c1 = lo + (hi - lo) / 4, hi - (hi - lo) / 4
    for _ in range(iters):
        a = [x for x in xs if abs(x - c0) <= abs(x - c1)]
        b = [x for x in xs if abs(x - c0) > abs(x - c1)]
        if not a or not b:
            return float("nan"), float("nan"), len(a), len(b)
        n0, n1 = statistics.fmean(a), statistics.fmean(b)
        if n0 == c0 and n1 == c1:
            break
        c0, c1 = n0, n1
    return c0, c1, len(a), len(b)


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt(x, nd=4):
    return "nan" if x != x else f"{x:.{nd}f}"


# ---------------------------------------------------------------- load


def load(path):
    raw = json.load(open(path))
    rows = []
    for s in raw:
        m = s.get("officialMetrics")
        if not m or not m.get("passed_correctness"):
            continue
        if m.get("checked_steps") != 1344 or m.get("case_count") != 11:
            continue
        need = (
            "prefill_seconds_per_token",
            "decode_seconds_per_token",
            "baseline_prefill_seconds_per_token",
            "baseline_decode_seconds_per_token",
        )
        if any(m.get(k) in (None, 0) for k in need):
            continue
        rows.append(
            {
                "id": s.get("id", ""),
                "solver": s.get("solverUsername", ""),
                "created": s.get("createdAt", ""),
                "sha": (s.get("submissionCommitSha") or "")[:12],
                "harness": m.get("harness_hash", ""),
                "score": s.get("officialScore"),
                "cand_pre": m["prefill_seconds_per_token"] * 1e6,  # us/token
                "cand_dec": m["decode_seconds_per_token"] * 1e3,  # ms/token
                "base_pre": m["baseline_prefill_seconds_per_token"] * 1e6,
                "base_dec": m["baseline_decode_seconds_per_token"] * 1e3,
            }
        )
    return rows


# ---------------------------------------------------------------- report

SERIES = ("cand_pre", "cand_dec", "base_pre", "base_dec")
LABEL = {
    "cand_pre": "candidate prefill us/tok",
    "cand_dec": "candidate decode  ms/tok",
    "base_pre": "baseline  prefill us/tok",
    "base_dec": "baseline  decode  ms/tok",
}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs_r2.json"
    rows = load(path)
    print(f"# receipt arm asymmetry -- {path}")
    print(f"current-generation passing receipts (checked_steps=1344, case_count=11): {len(rows)}")

    # baseline-free content score `ns`: paired baseline replaced by the pooled
    # cohort median baseline, so ns is a pure function of candidate timings.
    ref_pre = statistics.median(r["base_pre"] for r in rows)
    ref_dec = statistics.median(r["base_dec"] for r in rows)
    print(f"pooled median baseline: prefill {ref_pre:.3f} us/tok  decode {ref_dec:.5f} ms/tok")
    for r in rows:
        r["ns"] = (ref_dec / r["cand_dec"]) ** 0.75 * (ref_pre / r["cand_pre"]) ** 0.25

    print("\n## 1. global spread per series (candidate spread also contains real code differences)")
    for k in SERIES:
        xs = [r[k] for r in rows]
        print(
            f"  {LABEL[k]}: n={len(xs)} mean={statistics.fmean(xs):.5f} "
            f"rel_sd={100*rel_sd(xs):.3f}%  min={min(xs):.5f} max={max(xs):.5f}"
        )
    for k in ("score", "ns"):
        xs = [r[k] for r in rows if r[k] is not None]
        print(f"  {k}: n={len(xs)} mean={statistics.fmean(xs):.5f} rel_sd={100*rel_sd(xs):.3f}%")

    # ---------------- 2. harness_hash families
    fam = defaultdict(list)
    for r in rows:
        if r["harness"]:
            fam[r["harness"]].append(r)
    multi = {h: g for h, g in fam.items() if len(g) >= 2}
    print(f"\n## 2. harness_hash families: {len(fam)} distinct, {len(multi)} with n>=2")
    sizes = Counter(len(g) for g in fam.values())
    print("  family size histogram:", dict(sorted(sizes.items())))

    # do families hold one candidate archive?  check sha agreement + day span
    same_sha = sum(1 for g in multi.values() if len({r["sha"] for r in g}) == 1)
    print(f"  families whose members share one submissionCommitSha: {same_sha}/{len(multi)}")
    spans = []
    for g in multi.values():
        ds = sorted(parse_dt(r["created"]) for r in g)
        spans.append((ds[-1] - ds[0]).total_seconds() / 86400.0)
    if spans:
        print(
            f"  family day-span: median {statistics.median(spans):.3f}d  "
            f"max {max(spans):.3f}d  families spanning >0.5d: {sum(1 for s in spans if s > 0.5)}"
        )

    print("\n  pooled WITHIN-family spread (same harness_hash => same candidate archive hypothesis):")
    for k in SERIES + ("score", "ns"):
        groups = [[r[k] for r in g] for g in multi.values()]
        sd, dof = pooled_within_rel_sd(groups)
        lab = LABEL.get(k, k)
        print(f"    {lab}: pooled rel_sd={100*sd:.3f}%  dof={dof}")

    # ---------------- 3. correlation between the two arms
    print("\n## 3. do the two arms co-move?  (a shared session factor would show up here)")

    def report_corr(tag, xs, ys):
        r = pearson(xs, ys)
        rs = spearman(xs, ys)
        lo, hi = corr_ci95(r, len(xs))
        print(
            f"    {tag}: n={len(xs)} pearson={fmt(r,3)} [95% {fmt(lo,3)},{fmt(hi,3)}] "
            f"spearman={fmt(rs,3)}"
        )

    print("  raw values, all current-generation receipts:")
    report_corr("base_pre vs cand_pre", [r["base_pre"] for r in rows], [r["cand_pre"] for r in rows])
    report_corr("base_dec vs cand_dec", [r["base_dec"] for r in rows], [r["cand_dec"] for r in rows])
    report_corr("base_pre vs base_dec", [r["base_pre"] for r in rows], [r["base_dec"] for r in rows])
    report_corr("cand_pre vs cand_dec", [r["cand_pre"] for r in rows], [r["cand_dec"] for r in rows])

    # frontier-tight cohort: top decile ns => candidate content is ~fixed
    rows_ns = sorted(rows, key=lambda r: -r["ns"])
    tight = rows_ns[: max(20, len(rows_ns) // 10)]
    print(
        f"\n  frontier-tight cohort (top-decile ns, n={len(tight)}): candidate content nearly fixed,"
    )
    for k in SERIES:
        xs = [r[k] for r in tight]
        print(f"    {LABEL[k]}: rel_sd={100*rel_sd(xs):.3f}%")
    report_corr("base_pre vs cand_pre", [r["base_pre"] for r in tight], [r["cand_pre"] for r in tight])
    report_corr("base_dec vs cand_dec", [r["base_dec"] for r in tight], [r["cand_dec"] for r in tight])

    # within-family residual correlation.  NOTE: harness_hash families turn out
    # to be ~1.6h temporal epochs, not byte-identical archives (see section 2),
    # so this removes epoch-level effects, not content.
    print("\n  within-epoch residuals (harness_hash cluster means removed):")
    for a, b in (("base_pre", "cand_pre"), ("base_dec", "cand_dec"), ("base_pre", "base_dec")):
        rx, ry = [], []
        for g in multi.values():
            if len(g) < 2:
                continue
            ma = statistics.fmean(r[a] for r in g)
            mb = statistics.fmean(r[b] for r in g)
            for r in g:
                rx.append(r[a] / ma - 1.0)
                ry.append(r[b] / mb - 1.0)
        if len(rx) >= 4:
            report_corr(f"{a} vs {b}", rx, ry)

    # ---------------- 4. bimodality of the baseline arm
    print("\n## 4. baseline-arm bimodality, and does the candidate arm follow it?")
    bp = [r["base_pre"] for r in rows]
    c0, c1, n0, n1 = two_means_1d(bp)
    print(
        f"  base_pre 2-means: low centre {c0:.3f} (n={n0})  high centre {c1:.3f} (n={n1})  "
        f"gap {100*(c1/c0-1):.2f}%"
    )
    cut = (c0 + c1) / 2
    lo_g = [r for r in rows if r["base_pre"] <= cut]
    hi_g = [r for r in rows if r["base_pre"] > cut]
    for k in SERIES + ("score", "ns"):
        a = statistics.fmean(r[k] for r in lo_g)
        b = statistics.fmean(r[k] for r in hi_g)
        print(f"    {LABEL.get(k,k)}: low-mode mean {a:.5f}  high-mode mean {b:.5f}  ratio {b/a:.5f}")

    # ---------------- 5. is the baseline arm drifting with calendar time?
    print("\n## 5. baseline arm vs calendar day (session/epoch structure)")
    byday = defaultdict(list)
    for r in rows:
        byday[r["created"][:10]].append(r)
    days = sorted(byday)
    print(f"  {len(days)} distinct days, {days[0]} .. {days[-1]}")
    print("  day        n   base_pre_mean  base_pre_relsd  base_dec_mean  cand_pre_mean")
    for d in days:
        g = byday[d]
        if len(g) < 3:
            continue
        print(
            f"  {d}  {len(g):3d}   {statistics.fmean(r['base_pre'] for r in g):11.3f}  "
            f"{100*rel_sd([r['base_pre'] for r in g]):13.3f}%  "
            f"{statistics.fmean(r['base_dec'] for r in g):12.5f}  "
            f"{statistics.fmean(r['cand_pre'] for r in g):12.3f}"
        )
    within = [[r["base_pre"] for r in g] for g in byday.values() if len(g) >= 2]
    sd_w, dof_w = pooled_within_rel_sd(within)
    print(
        f"  base_pre: pooled WITHIN-day rel_sd={100*sd_w:.3f}% (dof={dof_w}) vs "
        f"global {100*rel_sd(bp):.3f}%"
    )
    dm = [statistics.fmean(g) for g in within]
    print(f"  base_pre: BETWEEN-day rel_sd of day means={100*rel_sd(dm):.3f}% (n_days={len(dm)})")

    # ---------------- 5b. mode split with content held ~fixed
    print("\n## 5b. base_pre mode split inside the frontier-tight cohort (content ~fixed)")
    tl = [r for r in tight if r["base_pre"] <= cut]
    th = [r for r in tight if r["base_pre"] > cut]
    print(f"  low-mode n={len(tl)}  high-mode n={len(th)}")
    if tl and th:
        for k in SERIES + ("score", "ns"):
            a = statistics.fmean(r[k] for r in tl)
            b = statistics.fmean(r[k] for r in th)
            print(
                f"    {LABEL.get(k,k)}: low {a:.5f}  high {b:.5f}  ratio {b/a:.5f} "
                f"({100*(b/a-1):+.2f}%)"
            )

    # ---------------- 6. ground-truth replicate noise from byte-identical code
    print("\n## 6. replicate noise on BYTE-IDENTICAL candidate code (ground truth)")
    triples = {
        "program.md control triple (byte-identical)": ("f8502e12", "71586bcf", "f3cda678"),
        "PR40 r1 arms (v0/v2/v1, behaviourally near-identical)": (
            "c3ce66ec",
            "cdf71faf",
            "4058d0b4",
        ),
    }
    model = {}
    for name, ids in triples.items():
        g = [r for r in rows for i in ids if r["id"].startswith(i)]
        if len(g) != len(ids):
            print(f"  {name}: only {len(g)}/{len(ids)} found, skipped")
            continue
        print(f"\n  {name}  n={len(g)}  days={sorted({r['created'][:10] for r in g})}")
        st = {}
        for k in SERIES + ("score", "ns"):
            xs = [r[k] for r in g]
            st[k] = rel_sd(xs)
            print(f"    {LABEL.get(k,k)}: mean={statistics.fmean(xs):.6f} rel_sd={100*st[k]:.3f}%")
        pred_ns = math.hypot(0.75 * st["cand_dec"], 0.25 * st["cand_pre"])
        pred_sc = math.hypot(
            0.75 * math.hypot(st["cand_dec"], st["base_dec"]),
            0.25 * math.hypot(st["cand_pre"], st["base_pre"]),
        )
        print(
            f"    model: predicted sd(ns)={100*pred_ns:.3f}% (measured {100*st['ns']:.3f}%)  "
            f"predicted sd(score)={100*pred_sc:.3f}% (measured {100*st['score']:.3f}%)"
        )
        share = (0.25 * st["base_pre"] / pred_sc) ** 2
        print(f"    baseline-PREFILL draw alone explains {100*share:.1f}% of officialScore variance")
        model[name] = (pred_ns, pred_sc)

    key = "program.md control triple (byte-identical)"
    if key in model:
        pn, ps = model[key]
        print("\n  min detectable TRUE content delta (95% two-sided), byte-identical arm sds:")
        for k in (1, 2, 3):
            print(
                f"    paired A/B, k={k} receipts per arm: ns "
                f"{100*1.96*math.sqrt(2)*pn/math.sqrt(k):.3f}%   officialScore "
                f"{100*1.96*math.sqrt(2)*ps/math.sqrt(k):.3f}%"
            )
        print(
            f"    single receipt vs a FIXED published control: ns {100*1.96*pn:.3f}%   "
            f"officialScore {100*1.96*ps:.3f}%"
        )

    # ---------------- 7. empirical baseline-lottery distribution
    print("\n## 7. empirical baseline lottery  L = officialScore / ns")
    for r in rows:
        r["L"] = r["score"] / r["ns"]
    Ls = sorted(r["L"] for r in rows)
    print(f"  n={len(Ls)}  rel_sd={100*rel_sd(Ls):.3f}%")
    for q in (0, 1, 5, 25, 50, 75, 95, 99, 100):
        i = min(len(Ls) - 1, max(0, round(q / 100 * (len(Ls) - 1))))
        print(f"    p{q:<3d} L={Ls[i]:.6f}  ({100*(Ls[i]-1):+.3f}%)")

    best_r = max(rows, key=lambda r: r["score"])
    best = best_r["score"]
    pct = 100 * sum(1 for x in Ls if x <= best_r["L"]) / len(Ls)
    print(
        f"\n  current best officialScore {best:.6f} ({best_r['id'][:8]}, {best_r['solver']}, "
        f"ns={best_r['ns']:.6f}, its L={best_r['L']:.6f} = p{pct:.1f})"
    )
    ctrl = [r for r in rows if r["id"].startswith("c3ce66ec")]
    if ctrl:
        c = ctrl[0]
        print(
            f"  our control c3ce66ec ns={c['ns']:.6f}: content is "
            f"{100*(c['ns']/best_r['ns']-1):+.3f}% faster than the crown holder's"
        )
        need = best / c["ns"]
        p = sum(1 for x in Ls if x > need) / len(Ls)
        odds = f"~1 in {1/p:.0f} receipts" if p > 0 else "never observed in 893 receipts"
        print(f"  to OUTRANK it, this same code needs L>{need:.6f}; empirical P={100*p:.2f}% ({odds})")
        for tp in (0.50, 0.80, 0.95):
            i = min(len(Ls) - 1, max(0, round((1 - tp) * (len(Ls) - 1))))
            nn = best / Ls[i]
            print(
                f"  for P(outrank)>={100*tp:.0f}% on one receipt we need ns>={nn:.6f}, i.e. "
                f"{100*(nn/c['ns']-1):+.3f}% further content gain"
            )

    # ---------------- 8. named receipts
    print("\n## 8. named receipts")
    want = ("f8502e12", "71586bcf", "f3cda678", "c3ce66ec", "cdf71faf", "4058d0b4", "46eeccf")
    for w in want:
        hit = [r for r in rows if r["id"].startswith(w)]
        for r in hit:
            print(
                f"  {r['id'][:8]} {r['created'][:19]} {r['solver'][:14]:14s} "
                f"cand_pre={r['cand_pre']:.3f} cand_dec={r['cand_dec']:.5f} "
                f"base_pre={r['base_pre']:.3f} base_dec={r['base_dec']:.5f} "
                f"score={r['score']:.6f} ns={r['ns']:.6f} L={r['L']:.6f} "
                f"harness={r['harness'][:8]}"
            )
        if not hit:
            print(f"  {w}: not found in current-generation passing cohort")


if __name__ == "__main__":
    main()
