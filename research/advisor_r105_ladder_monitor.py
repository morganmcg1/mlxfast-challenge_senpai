#!/usr/bin/env python3
"""Live monitor of this campaign's ranked-receipt ladders, read off the API.

WHY THIS EXISTS
---------------
Students submit official receipts long before they push the write-up to their
pull request.  Between the submission and the push the advisor is blind if the
only instrument is `git`.  It turns out the campaign is not blind at all: every
receipt carries a free-text `note`, and the students put their pre-registered
arm label in it.  So the submission feed *is* a live progress channel.

🔴 ROUND-106 CORRECTION -- THE PARAGRAPH THAT USED TO BE HERE WAS WRONG.

This docstring previously "settled" a round-105 scare by concluding that the
`morganmcg1` solver account is NOT shared with a sibling campaign.  **That
conclusion is false and is retracted.**  Rule 93.1 establishes by direct
enumeration that the fork hosts at least THREE concurrent launches -- `maple`
(ours), `cedar` and `birch` -- with 133 / 236 / 250 student branches and three
separate advisor branches, and that all three submit through the single
`morganmcg1` account.  Of 84 scored records, note-text attribution gives
maple 29, birch 3, cedar 2, and **50 unattributed**.

What the old paragraph got RIGHT, and what still stands:

  * The notes are a live progress channel.  Students put their preregistered
    arm label in the free-text `note` long before they push a write-up, so the
    submission feed really does show mid-ladder progress.
  * `git cat-file` failing on a `submissionCommitSha` is NOT evidence of
    foreign provenance -- it usually just means the advisor has not fetched
    that submission commit.  Never attribute on that basis.

What it got WRONG, and what replaces it:

  * The `submissionCommitSha` is an IDENTITY, not an OWNER.  It cannot
    attribute a receipt to a launch.
  * Neither can `solverUsername` (constant), `golden_hash` (constant across
    all three launches), `weights_hash` (likewise), or `harness_hash` -- which
    is emphatically NOT a launch fingerprint: 68 distinct values over 84
    receipts.
  * **Only the free-text `note` attributes a receipt to a launch.**  If the
    note does not say, the receipt is UNATTRIBUTED and must not be pooled into
    any maple-specific statistic.

  Standing rule: attribute by `note` text.  Treat every pooled statistic over
  this corpus as a MIXTURE unless it was filtered by note first -- including
  rules 89.1 / 89.2 and the merit table.  Rule 88's ~2.7 receipts/hour is the
  ACCOUNT aggregate; our own share is ~0.9/hour.

READ-ONLY.

Usage:
    python3 research/advisor_r105_ladder_monitor.py [--since ISO8601]
                                                    [--who NAME]
                                                    [--full ARM]
"""
import argparse
import json
import math
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
MB_D = 0.013855009542
MB_P = 0.000372473193
OUR_CS = 2.583111
SD_LN_CS = 0.001860      # identical-code floor, trimmed dof 14


def token():
    t = os.environ.get("MLXFAST_API_TOKEN")
    if t:
        return t
    p = pathlib.Path.home() / ".config" / "mlxfast" / "config.json"
    if p.exists():
        return json.loads(p.read_text()).get("token")
    return None


def get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def ts_of(s):
    m = s.get("officialMetrics")
    if isinstance(m, dict) and m.get("timestamp"):
        return str(m["timestamp"])
    return str(s.get("createdAt") or s.get("updatedAt") or "")


def metrics(s):
    m = s.get("officialMetrics")
    if not isinstance(m, dict):
        return None, None, None
    d = m.get("decode_seconds_per_token")
    p = m.get("prefill_seconds_per_token")
    if not (d and p):
        return None, None, None
    return d * 1e6, p * 1e6, (MB_D / d) ** 0.75 * (MB_P / p) ** 0.25


TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)
ARM_RE = re.compile(r"^\*\*Arm:?\*\*\s*[`\"]?([A-Za-z0-9_.-]+)", re.M)
ROLE_RE = re.compile(r"^\*\*Role of this leg:?\*\*\s*(.+)$", re.M)
LEG_RE = re.compile(r"leg\s+(\d+)\s+of\s+(\d+)\s*[—-]\s*arm\s+([A-Za-z0-9_]+)", re.I)


def label(note):
    """(campaign-tag, arm-label, one-line description) parsed out of a note."""
    note = note or ""
    title = ""
    mt = TITLE_RE.search(note)
    if mt:
        title = mt.group(1).strip()
    tag = ""
    # Rule 93.1 bug fix: this used to be `\br(?:10\d)-[A-Za-z]\b` -- case
    # sensitive on a lowercase `r`, and limited to rounds 100-109.  Students
    # correctly write `R105-B`, so every properly-labelled receipt was being
    # reported as "(untagged)".  Now: case-insensitive, any 3-digit round, and
    # we fall back to the whole note body if the H1 title does not carry it.
    mtag = re.search(r"\bR\d{3}-[A-Za-z]\b", title, re.I) or re.search(
        r"\bR\d{3}-[A-Za-z]\b", note, re.I
    )
    if mtag:
        tag = mtag.group(0).upper()
    arm = ""
    ma = ARM_RE.search(note)
    if ma:
        arm = ma.group(1)
    else:
        ml = LEG_RE.search(title)
        if ml:
            arm = f"{ml.group(3)}/leg{int(ml.group(1)):02d}of{ml.group(2)}"
    desc = ""
    mr = ROLE_RE.search(note)
    if mr:
        desc = mr.group(1).strip()
    elif ma:
        line = note[ma.start():].splitlines()[0]
        desc = line.split("-", 1)[1].strip() if "-" in line else ""
    return tag or "(untagged)", arm or "(unlabelled)", desc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-09T00:00:00Z")
    ap.add_argument("--who", default="morganmcg1")
    ap.add_argument("--full", default=None,
                    help="print the entire note body for this arm label")
    a = ap.parse_args()

    tok = token()
    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))

    rows = [s for s in subs
            if s.get("solverUsername") == a.who and ts_of(s) >= a.since]
    rows.sort(key=ts_of)
    print(f"benchmark {bid}   {len(subs)} raw records   "
          f"{len(rows)} for {a.who} since {a.since}\n")

    ladders = {}
    print(f"{'timestamp':26s} {'commit':13s} {'ladder':10s} {'arm':22s} "
          f"{'dec us':>9s} {'pre us':>8s} {'cs':>9s} {'vs ours':>9s} status")
    print("-" * 128)
    for s in rows:
        d, p, cs = metrics(s)
        tag, arm, desc = label(s.get("note"))
        sha = (s.get("submissionCommitSha") or "")[:12] or "-"
        delta = f"{100 * (cs / OUR_CS - 1):+.3f}%" if cs else "    -    "
        print(f"{ts_of(s):26s} {sha:13s} {tag:10s} {arm:22s} "
              f"{d if d else float('nan'):9.3f} {p if p else float('nan'):8.4f} "
              f"{cs if cs else float('nan'):9.6f} {delta:>9s} {s.get('status')}")
        if cs:
            ladders.setdefault(tag, []).append((ts_of(s), arm, cs, d, p))
        if a.full and arm == a.full:
            print("\n" + "=" * 78)
            print(s.get("note") or "")
            print("=" * 78 + "\n")

    # --- per-ladder contrasts -------------------------------------------
    for tag, items in sorted(ladders.items()):
        if len(items) < 2:
            continue
        print(f"\n=== ladder {tag}: {len(items)} scored receipts ===")
        by_arm = {}
        for ts, arm, cs, d, p in items:
            by_arm.setdefault(re.split(r"[-/]", arm)[0], []).append((arm, cs, d))
        for base_arm, vals in sorted(by_arm.items()):
            csv = [c for _, c, _ in vals]
            dv = [x for _, _, x in vals]
            gm = math.exp(sum(math.log(c) for c in csv) / len(csv))
            sd = (math.sqrt(sum((math.log(c) - math.log(gm)) ** 2
                                for c in csv) / (len(csv) - 1))
                  if len(csv) > 1 else float("nan"))
            print(f"  {base_arm:8s} n={len(csv)}  geo-mean cs {gm:.6f}  "
                  f"mean decode {sum(dv) / len(dv):9.3f} us  "
                  f"sd(ln cs) {100 * sd if sd == sd else float('nan'):6.4f} %  "
                  f"[{', '.join(f'{c:.6f}' for c in csv)}]")
        # contrast every non-control arm against the pooled control arm
        controls = [k for k in by_arm if k.upper().startswith("A0")
                    or k.upper() in ("A", "CONTROL", "BASE")]
        if len(controls) == 1 and len(by_arm) > 1:
            ck = controls[0]
            cvals = [c for _, c, _ in by_arm[ck]]
            cgm = math.exp(sum(math.log(c) for c in cvals) / len(cvals))
            csd = (math.sqrt(sum((math.log(c) - math.log(cgm)) ** 2
                                 for c in cvals) / (len(cvals) - 1))
                   if len(cvals) > 1 else SD_LN_CS)
            use_sd = max(csd, SD_LN_CS)
            print(f"\n  control {ck}: n={len(cvals)} geo-mean {cgm:.6f}, "
                  f"observed sd(ln cs) {100 * csd:.4f} % "
                  f"(floor {100 * SD_LN_CS:.4f} %; using {100 * use_sd:.4f} %)")
            for k, vals in sorted(by_arm.items()):
                if k == ck:
                    continue
                av = [c for _, c, _ in vals]
                agm = math.exp(sum(math.log(c) for c in av) / len(av))
                d_ln = math.log(agm) - math.log(cgm)
                se = use_sd * math.sqrt(1.0 / len(av) + 1.0 / len(cvals))
                print(f"  {k:8s} vs {ck}: {100 * d_ln:+.4f} % of cs  "
                      f"z = {d_ln / se:+.2f}  "
                      f"95 % CI [{100 * (d_ln - 1.96 * se):+.4f} %, "
                      f"{100 * (d_ln + 1.96 * se):+.4f} %]  "
                      f"(n {len(av)} vs {len(cvals)})")
            print("  NOTE: n=1 arms carry the identical-code floor only as a "
                  "LOWER bound on their true spread; do not call a verdict off "
                  "a single receipt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
