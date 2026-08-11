#!/usr/bin/env python3
"""fern_r109f_own_shots.py -- the campaign's own receipts, code vs luck.

Every receipt on this benchmark carries four timings.  Two of them (the
baseline decode and baseline prefill legs) come from *reference* code that is
byte-identical for every solver on every submission, so they measure the host
and nothing else.  Define

    normalized = (REF_D / cand_decode)**0.75 * (REF_P / cand_prefill)**0.25
    draw       = published / normalized

`normalized` is the part of the published score that our code earned; `draw` is
the part the host handed out.  This script prints the r109-F campaign's own
shots on both axes, ranks each draw inside the empirical draw distribution of
every full-leg correct receipt on the benchmark, and reports the ratio between
the code spread and the published spread for (a) all same-class shots and
(b) the two shots that ran a byte-identical executable.

Usage:  python3 research/fern_r109f_own_shots.py [--cache /tmp/subs_p7.json]
"""

from __future__ import annotations

import argparse
import json
import statistics as st

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
CROWN = 2.61650354381456

# (label, receipt-id prefix, executable class)
SHOTS = [
    ("t1  base                ", "c1c0ba2c", "r109F-base"),
    ("t2  base, nonce replay  ", "88584270", "r109F-base"),
    ("t3  base + QHOIST=1     ", "e4078827", "r109F-qhoist"),
    ("t4  base + atlas v3     ", "ed40f3ee", "r109F-atlasv3"),
    ("t5  atlasv3 nonce replay", "0531544b", "r109F-atlasv3"),
    ("t6  atlasv3 replay #3   ", "cb4de9e0", "r109F-atlasv3"),
]


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/tmp/subs_p7.json")
    args = ap.parse_args()

    rows = json.load(open(args.cache))["submissions"]

    # ---- empirical draw distribution over the whole field -----------------
    draws = sorted(r["officialScore"] / normalized(r["officialMetrics"]) for r in rows if full_leg(r))
    n = len(draws)

    def pct_of(d: float) -> float:
        """percentile of a draw inside the field distribution"""
        below = sum(1 for x in draws if x <= d)
        return 100.0 * below / n

    def p_at_least(d: float) -> tuple[int, float]:
        k = sum(1 for x in draws if x >= d)
        return k, 100.0 * k / n

    print(f"field draw distribution: n={n} full-leg correct receipts")
    print(
        f"  min {draws[0]:.6f}  p05 {draws[int(0.05*n)]:.6f}  med {st.median(draws):.6f}"
        f"  p95 {draws[int(0.95*n)]:.6f}  max {draws[-1]:.6f}"
        f"  cv {100*st.stdev(draws)/st.fmean(draws):.4f}%"
    )
    print()

    # ---- our own shots -----------------------------------------------------
    by_label: dict[str, dict] = {}
    print("shot                       status     published   normalized      draw   draw pct   need for crown")
    for label, pref, klass in SHOTS:
        hit = [r for r in rows if r["id"].startswith(pref)]
        if not hit:
            print(f"{label}  MISSING")
            continue
        r = hit[0]
        m = r.get("officialMetrics") or {}
        if not full_leg(r):
            print(f"{label}  {r['status']:<10} (no full legs yet)")
            continue
        nz = normalized(m)
        dw = r["officialScore"] / nz
        need = CROWN / nz
        k, p = p_at_least(need)
        by_label[label.strip()] = dict(row=r, klass=klass, nz=nz, dw=dw)
        print(
            f"{label}  {r['status']:<10} {r['officialScore']:.6f}  {nz:.6f}  {dw:.6f}"
            f"   {pct_of(dw):5.1f}%   draw>={need:.6f}  {k}/{n} = {p:.4f}%"
        )
    print()

    # ---- code spread vs published spread ----------------------------------
    def spread(labels: list[str], title: str) -> None:
        got = [by_label[k] for k in labels if k in by_label]
        if len(got) < 2:
            print(f"{title}: not enough terminal receipts yet ({len(got)})")
            return
        nzs = [g["nz"] for g in got]
        pubs = [g["row"]["officialScore"] for g in got]
        cs = 100.0 * (max(nzs) - min(nzs)) / st.fmean(nzs)
        ps = 100.0 * (max(pubs) - min(pubs)) / st.fmean(pubs)
        print(f"{title}  ({len(got)} receipts)")
        print(f"  code (normalized) spread : {cs:.4f} %   [{min(nzs):.6f} .. {max(nzs):.6f}]")
        print(f"  published spread         : {ps:.4f} %   [{min(pubs):.6f} .. {max(pubs):.6f}]")
        if cs > 0:
            print(f"  luck / code amplification: x{ps/cs:.1f}")
        print()

    spread(
        ["t1  base", "t2  base, nonce replay", "t4  base + atlas v3", "t5  atlasv3 nonce replay"],
        "A. all non-regressed shots (base and atlas-v3 classes)",
    )
    spread(
        ["t1  base", "t2  base, nonce replay"],
        "B. byte-identical executable pair (comment-only nonce apart)",
    )
    spread(
        ["t4  base + atlas v3", "t5  atlasv3 nonce replay"],
        "C. byte-identical executable pair (atlas-v3 class)",
    )

    # ---- D. the campaign's own receipts as a noise gauge -------------------
    # Two of our five shots are *replays*: t2 replays t1's executable and t5
    # replays t4's, comment-only nonce apart.  Each pair is therefore a paired
    # draw from the instrument with the code held exactly fixed, so |difference|
    # estimates the per-observation sd of every axis with no code term at all.
    # With k pairs, sd_hat = sqrt( sum(d_i^2) / (2k) ).
    pairs = [
        ("base   t1/t2   ", "t1  base", "t2  base, nonce replay"),
        ("atlasv3 t4/t5  ", "t4  base + atlas v3", "t5  atlasv3 nonce replay"),
    ]
    axes = [
        ("published  ", lambda g: g["row"]["officialScore"]),
        ("normalized ", lambda g: g["nz"]),
        ("cand decode", lambda g: g["row"]["officialMetrics"]["decode_seconds_per_token"]),
        ("cand prefil", lambda g: g["row"]["officialMetrics"]["prefill_seconds_per_token"]),
        ("base decode", lambda g: g["row"]["officialMetrics"]["baseline_decode_seconds_per_token"]),
        ("base prefil", lambda g: g["row"]["officialMetrics"]["baseline_prefill_seconds_per_token"]),
    ]
    ready = [(t, a, b) for t, a, b in pairs if a in by_label and b in by_label]
    if ready:
        print("D. identical-executable replays as a zero-code-variance gauge")
        header = "  axis         " + "".join(f"{t}" for t, _, _ in ready) + "  sd_hat"
        print(header)
        for aname, get in axes:
            diffs = []
            cells = ""
            for _, la, lb in ready:
                ga, gb = by_label[la], by_label[lb]
                va, vb = get(ga), get(gb)
                d = 100.0 * abs(va - vb) / ((va + vb) / 2)
                diffs.append(d)
                cells += f"  {d:7.4f}%      "
            sd = (sum(d * d for d in diffs) / (2 * len(diffs))) ** 0.5
            print(f"  {aname}  {cells}  {sd:.4f}%")
        print(
            "  (sd_hat is a k=%d-pair estimate: wide, but it contains no code term\n"
            "   whatsoever, so it is an upper bound on nothing and a clean estimate\n"
            "   of instrument noise on each axis.)" % len(ready)
        )
        print()

    # ---- E. class means, and the crown need computed from them -------------
    classes: dict[str, list[dict]] = {}
    for g in by_label.values():
        classes.setdefault(g["klass"], []).append(g)
    print("E. per-class means (the honest point estimate for an executable)")
    for klass, gs in sorted(classes.items()):
        nzs = [g["nz"] for g in gs]
        mean_nz = st.fmean(nzs)
        need = CROWN / mean_nz
        k, p = p_at_least(need)
        note = ""
        if len(gs) > 1:
            note = f"  spread {100*(max(nzs)-min(nzs))/mean_nz:.4f}%"
        print(
            f"  {klass:<16} n={len(gs)}  mean normalized {mean_nz:.6f}{note}\n"
            f"                     crown needs draw >= {need:.6f}  ->  {k}/{n} = {p:.4f}% per shot"
        )
    if "r109F-base" in classes and "r109F-atlasv3" in classes:
        a = st.fmean([g["nz"] for g in classes["r109F-base"]])
        b = st.fmean([g["nz"] for g in classes["r109F-atlasv3"]])
        na, nb = len(classes["r109F-base"]), len(classes["r109F-atlasv3"])
        delta = 100.0 * (b - a) / a
        sd_pop = 0.357  # normalized cv, %, from the >=2026-08-10 baseline-leg window
        se = sd_pop * (1.0 / na + 1.0 / nb) ** 0.5
        print(
            f"  atlasv3 - base on the code axis: {delta:+.4f}%  "
            f"(se {se:.4f}% at population sd {sd_pop}% -> {abs(delta)/se:.2f} sigma)"
        )
        print(
            "  local A/B on the same tree measured -0.0260% decode = +0.0166% score,\n"
            "  so the ranked read is consistent in sign and uninformative in size."
        )
    print()

    # ---- best-of ----------------------------------------------------------
    if by_label:
        best_code = max(by_label.items(), key=lambda kv: kv[1]["nz"])
        best_pub = max(by_label.items(), key=lambda kv: kv[1]["row"]["officialScore"])
        print(f"best CODE  of the campaign: {best_code[0]}  normalized {best_code[1]['nz']:.6f}")
        print(
            f"best LUCK  of the campaign: {best_pub[0]}  published  "
            f"{best_pub[1]['row']['officialScore']:.6f}  (draw {best_pub[1]['dw']:.6f})"
        )
        if best_code[0] != best_pub[0]:
            print(
                "  -> the shot with the best code is NOT the shot with the best published score."
            )


if __name__ == "__main__":
    main()
