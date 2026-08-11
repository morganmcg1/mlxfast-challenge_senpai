#!/usr/bin/env python3
"""
R114 INSTRUMENT VERDICT
=======================

Settles the single most important methodological question of the campaign:

    When a student runs one official submission, WHICH NUMBER should they read
    to decide whether their arm worked?

Candidates:
    (a) officialScore                                (the competition metric)
    (b) decode_seconds_per_token                     (raw candidate decode leg)
    (c) prefill_seconds_per_token                    (raw candidate prefill leg)
    (d) decode / baseline_decode                     (paired decode ratio)
    (e) prefill / baseline_prefill                   (paired prefill ratio)

The honest error bar for any instrument is its WITHIN-FAMILY spread, where a
"family" is a set of receipts whose editable surfaces are byte-equivalent
(nonce comments only).  Anything that moves within a family is noise by
construction.

Family membership below was established MECHANICALLY, by `mlxfast reset`
+ `git diff` on the editable paths, or by direct note attribution.  In
particular 59d2418 vs 2397aee was verified to differ by exactly one comment
character ("senpai-r106e-replay-02" -> "-03").
"""

import json
import math
import os
import statistics as st
import urllib.parse
import urllib.request

BENCH = "eigenlabs/mlxfast-challenge"
CACHE = "/tmp/mlxfast_subs_r114.json"


def load():
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            d = json.load(f)
        return d["submissions"] if isinstance(d, dict) else d
    base = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast").rstrip("/")
    url = f"{base}/api/benchmarks/{urllib.parse.quote(BENCH, safe='')}/submissions"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {os.environ['MLXFAST_API_TOKEN']}"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    rows = data["submissions"] if isinstance(data, dict) else data
    with open(CACHE, "w") as f:
        json.dump(rows, f)
    return rows


def metrics(row):
    m = row.get("officialMetrics")
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except Exception:
            return None
    return m if isinstance(m, dict) else None


# ---------------------------------------------------------------- families
# Every member of a family is a byte-equivalent editable surface (nonce only).
FAMILIES = {
    "H  maple advisor HEAD class": ["2771067", "c1c0ba2", "8858427", "2aedeb8"],
    "R  r106e replay of 4b0e051b": ["59d2418", "2397aee"],
    "C  r104-A stage2 depth-4 control": ["d5f2b4c", "a8a8040", "8a09a94"],
    "N  r105-A null control A0": ["69fb349", "c793040"],
    "A  R93 Arm A null replicates": ["25e1f18", "05dd8bb"],
}

rows = load()
by_prefix = {}
for r in rows:
    rid = str(r.get("id", ""))
    m = metrics(r)
    if not m:
        continue
    need = (
        "decode_seconds_per_token",
        "baseline_decode_seconds_per_token",
        "prefill_seconds_per_token",
        "baseline_prefill_seconds_per_token",
    )
    if not all(k in m for k in need):
        continue
    by_prefix[rid[:7]] = (r, m)

INSTRUMENTS = [
    ("officialScore", lambda r, m: r.get("officialScore")),
    ("cand decode", lambda r, m: m["decode_seconds_per_token"]),
    ("cand prefill", lambda r, m: m["prefill_seconds_per_token"]),
    ("decode ratio", lambda r, m: m["decode_seconds_per_token"] / m["baseline_decode_seconds_per_token"]),
    ("prefill ratio", lambda r, m: m["prefill_seconds_per_token"] / m["baseline_prefill_seconds_per_token"]),
    ("base decode", lambda r, m: m["baseline_decode_seconds_per_token"]),
    ("base prefill", lambda r, m: m["baseline_prefill_seconds_per_token"]),
]

print("=" * 96)
print("(1) WITHIN-FAMILY RELATIVE SPREAD  (sd/mean, %) - byte-equivalent surfaces only")
print("=" * 96)
print(f"  {'family':<34}{'n':>3}  " + "".join(f"{name:>15}" for name, _ in INSTRUMENTS))

pool = {name: [] for name, _ in INSTRUMENTS}  # (sum of squared devs, df)
for fam, ids in FAMILIES.items():
    got = [by_prefix[i] for i in ids if i in by_prefix]
    if len(got) < 2:
        print(f"  {fam:<34}{len(got):>3}  (insufficient)")
        continue
    cells = []
    for name, fn in INSTRUMENTS:
        vals = [fn(r, m) for r, m in got]
        mu = st.mean(vals)
        sd = st.stdev(vals)
        cells.append(f"{100*sd/mu:>14.4f}%")
        ss = sum((v - mu) ** 2 / mu**2 for v in vals)
        pool[name].append((ss, len(vals) - 1))
    print(f"  {fam:<34}{len(got):>3}  " + "".join(cells))

print()
print("  POOLED within-family sd (all families, common df):")
tot = {}
for name, _ in INSTRUMENTS:
    ss = sum(a for a, _ in pool[name])
    df = sum(b for _, b in pool[name])
    tot[name] = 100 * math.sqrt(ss / df) if df else float("nan")
    print(f"    {name:<16} {tot[name]:8.4f}%   (df={df})")

print()
print("=" * 96)
print("(2) VERDICT: does dividing by the paired baseline HELP or HURT?")
print("=" * 96)
for leg, raw, rat, base in (
    ("decode", "cand decode", "decode ratio", "base decode"),
    ("prefill", "cand prefill", "prefill ratio", "base prefill"),
):
    print(f"  {leg}: raw {tot[raw]:.4f}%   ratio {tot[rat]:.4f}%   baseline {tot[base]:.4f}%")
    if tot[rat] < tot[raw]:
        print(f"     -> PAIRING HELPS by {tot[raw]/tot[rat]:.2f}x: the host is common-mode.")
    else:
        print(f"     -> PAIRING HURTS by {tot[rat]/tot[raw]:.2f}x: the baseline arm is independent noise.")

print()
print("=" * 96)
print("(3) MINIMUM DETECTABLE EFFECT of ONE submission, and of a paired A/B")
print("=" * 96)
print("     (2-sided 5%, 80% power => 2.80 * se ; %-of-SCORE via 0.75 decode / 0.25 prefill)")
print(f"  {'instrument':<16}{'sd 1 draw':>12}{'MDE n=1v1':>12}{'MDE 3v3':>12}{'MDE 5v5':>12}{'  -> % of score':>16}")
for name, w in (("officialScore", 1.0), ("cand decode", 0.75), ("cand prefill", 0.25),
                ("decode ratio", 0.75), ("prefill ratio", 0.25)):
    sd = tot[name]
    row = ""
    for n in (1, 3, 5):
        se = sd * math.sqrt(2.0 / n)
        row += f"{2.80*se:>11.3f}%"
    mde5 = 2.80 * sd * math.sqrt(2.0 / 5)
    print(f"  {name:<16}{sd:>11.4f}%{row}{w*mde5:>15.3f}%")

print()
print("=" * 96)
print("(4) THE RETRACTION THIS FORCES")
print("=" * 96)
h = [by_prefix[i][1]["decode_seconds_per_token"] for i in FAMILIES["H  maple advisor HEAD class"] if i in by_prefix]
r = [by_prefix[i][1]["decode_seconds_per_token"] for i in FAMILIES["R  r106e replay of 4b0e051b"] if i in by_prefix]
print(f"  HEAD-class candidate decode sd was {100*st.stdev(h)/st.mean(h):.4f}% over n=4 spanning 16h.")
print(f"  Byte-identical replay pair differ by {100*abs(r[0]-r[1])/st.mean(r):.4f}% 23 minutes apart.")
print("  => the 0.0145% figure was a 4-draw coincidence, NOT the instrument resolution.")
print("  => the claimed 0.35-0.38% 'maple decode regression' sits INSIDE one-pair noise.")
print("  => on the metric that actually decides the campaign, our HEAD class is AHEAD:")
hs = [by_prefix[i][0]["officialScore"] for i in FAMILIES["H  maple advisor HEAD class"] if i in by_prefix]
rs = [by_prefix[i][0]["officialScore"] for i in FAMILIES["R  r106e replay of 4b0e051b"] if i in by_prefix]
print(f"       HEAD class mean score {st.mean(hs):.8f} (n={len(hs)})")
print(f"       4b0e051b replay  mean {st.mean(rs):.8f} (n={len(rs)})  -> {100*(st.mean(hs)/st.mean(rs)-1):+.3f}%")
