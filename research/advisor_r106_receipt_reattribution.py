#!/usr/bin/env python3
"""Re-attribute the shared `morganmcg1` receipt corpus to the maple launch.

WHY THIS EXISTS
---------------
Rule 93.1 established that the `morganmcg1` solver account is shared by at
least three concurrent Senpai launches (`maple` = ours, plus `cedar` and
`birch`), that no structured field separates them -- `solverUsername` is
constant, `golden_hash` and `weights_hash` are constant across all three, and
`harness_hash` takes 68 distinct values over 84 receipts so it is not a launch
fingerprint either -- and that therefore ONLY the free-text `note` attributes
a receipt.  Under the narrow ruleset used there, 84 scored receipts split
maple 29 / birch 3 / cedar 2 / **50 unattributed**.

Fifty unattributed receipts is 60 % of the corpus.  Every pooled statistic in
the research state that was not note-filtered -- rule 89.1's identical-tree
grouping, rule 89.2's channel sigma, the merit table, rule 93.2's f
distribution -- is a MIXTURE over an unknown blend of three launches.  This
script tries to shrink the unattributed pile with a WIDENED but still
falsifiable ruleset, so that maple-only statistics can be recomputed and so
that maple-nezuko's round-106-H channel-economics fit has a defensible
`launch_l` term instead of a guess.

ATTRIBUTION RULESET (ordered; first match wins; every hit is labelled)
---------------------------------------------------------------------
  S1 `note-branch`   note names a `maple-<student>` branch or student.
  S2 `note-student`  note names a bare maple student first name.  The four
                     maple students are frieren / fern / tanjiro / nezuko and
                     those names do not occur in the other launches' rosters,
                     so a bare first name is a maple marker.  This is the
                     widening that S1 missed.
  S3 `note-path`     note quotes a `research/maple-...` deliverable path or a
                     `research/r10*/`-style maple artefact directory.
  S4 `advisor-head`  note carries `Advisor HEAD is <sha>` and that sha is a
                     prefix of a commit reachable from the maple advisor
                     branch.  Exact, because we own that history.
  S5 `note-pr`       note cites a PR number that appears in the maple research
                     state and is not on the known-foreign list.
  S6 `time-adjacent` PROBABILISTIC ONLY, never used to claim ownership -- the
                     receipt lands within `--window-min` of a commit on a
                     fetched `maple-*` branch.  Reported separately as a
                     ceiling on how much more of the residual could be ours.

NON-SIGNALS, do not reintroduce them: `solverUsername`, `golden_hash`,
`weights_hash`, `harness_hash`, and `git cat-file` on `submissionCommitSha`
(absence from the local object store only means the advisor never fetched that
submission commit -- it is NOT evidence of foreign provenance).

ISOLATION: this script reads maple refs and the maple advisor branch only.  It
never fetches, reads or compares against another launch's branches, PRs or
trees.  Receipts that fail every maple test are reported as UNATTRIBUTED, not
as cedar or birch.

It also runs the round-93 loose end: group the corpus by
`submissionCommitSha` and hunt the partner of the calibration receipt whose
note says "an identical tree, submitted twice".

READ-ONLY with respect to the repository.  Needs MLXFAST_API_TOKEN.

Usage:
    python3 research/advisor_r106_receipt_reattribution.py \
        [--who morganmcg1] [--window-min 45] [--dump-residual 60] \
        [--json /tmp/r106_reattribution.json]
"""
import argparse
import collections
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
MB_D = 0.013855009542
MB_P = 0.000372473193

ADVISOR_REF = "codex/mlxfast-maple-20260804-advisor"
MAPLE_STUDENTS = ("frieren", "fern", "tanjiro", "nezuko")
# PRs that the isolation firewall names as belonging to other launches.
FOREIGN_PRS = {549, 604, 611, 613, 614, 618}

HEAD_RE = re.compile(r"Advisor HEAD is[^0-9a-f]*([0-9a-f]{7,40})")
BRANCH_RE = re.compile(r"\bmaple[-/](?:" + "|".join(MAPLE_STUDENTS) + r")\b", re.I)
STUDENT_RE = re.compile(r"\b(?:" + "|".join(MAPLE_STUDENTS) + r")\b", re.I)
PATH_RE = re.compile(r"research/(?:maple-|r10\d)", re.I)
PR_RE = re.compile(r"#(\d{2,4})\b")
OTHER_LAUNCH_RE = re.compile(r"\b(cedar|birch)[-/]?\w*", re.I)


def sh(args, cwd):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


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
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def ts_of(s):
    m = s.get("officialMetrics")
    if isinstance(m, dict) and m.get("timestamp"):
        return str(m["timestamp"])
    return str(s.get("createdAt") or s.get("updatedAt") or "")


def epoch(ts):
    # "2026-08-10T08:03:15Z" -> seconds, tolerant of fractional seconds.
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)", ts or "")
    if not m:
        return None
    import calendar
    return calendar.timegm(tuple(int(x) for x in m.groups()) + (0, 0, 0))


def maple_evidence(repo, window_min):
    """Collect the maple-only evidence sets from the local checkout."""
    heads = set()
    out = sh(["git", "rev-list", "--max-count=4000", ADVISOR_REF], repo)
    if not out:
        out = sh(["git", "rev-list", "--max-count=4000", "origin/" + ADVISOR_REF], repo)
    for line in out.split():
        for n in (7, 8, 10, 12, 40):
            heads.add(line[:n])

    refs = [r.strip() for r in sh(
        ["git", "for-each-ref", "--format=%(refname)", "refs/remotes/origin/maple-*"],
        repo).splitlines() if r.strip()]
    commit_times = []
    for r in refs:
        for line in sh(["git", "log", "--max-count=200", "--format=%cI", r], repo).splitlines():
            e = epoch(line.strip())
            if e is not None:
                commit_times.append(e)
    commit_times.sort()
    return heads, refs, commit_times, window_min * 60


def maple_pr_numbers(repo):
    doc = pathlib.Path(repo) / "research" / "CURRENT_RESEARCH_STATE.md"
    nums = set()
    if doc.exists():
        for m in PR_RE.finditer(doc.read_text(errors="ignore")):
            n = int(m.group(1))
            if 50 <= n <= 5000:
                nums.add(n)
    return nums - FOREIGN_PRS


def classify(note, heads, maple_prs):
    if BRANCH_RE.search(note):
        return "S1 note-branch"
    if STUDENT_RE.search(note):
        return "S2 note-student"
    if PATH_RE.search(note):
        return "S3 note-path"
    m = HEAD_RE.search(note)
    if m:
        sha = m.group(1)
        if sha in heads or sha[:12] in heads or sha[:7] in heads:
            return "S4 advisor-head"
    for pm in PR_RE.finditer(note):
        n = int(pm.group(1))
        if n in maple_prs and n not in FOREIGN_PRS:
            return "S5 note-pr"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="morganmcg1")
    ap.add_argument("--window-min", type=float, default=45.0)
    ap.add_argument("--dump-residual", type=int, default=60)
    ap.add_argument("--snippet", type=int, default=160)
    ap.add_argument("--note-grep", default=(
        r"identical tree|identical-tree|submitted twice|calibration submission|"
        r"calibration replicate|compile-identical|byte-identical twin|"
        r"\breplicate [A-Z]\b|\b[A-C] of [23]\b"))
    ap.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[1]))
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    tok = token()
    if not tok:
        print("no MLXFAST_API_TOKEN", file=sys.stderr)
        return 2

    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))
    rows = [s for s in subs if s.get("solverUsername") == a.who]
    rows.sort(key=ts_of)

    heads, refs, ctimes, window = maple_evidence(a.repo, a.window_min)
    maple_prs = maple_pr_numbers(a.repo)
    print(f"# corpus         : {len(rows)} receipts under {a.who}")
    print(f"# maple advisor  : {ADVISOR_REF}, "
          f"{len([h for h in heads if len(h) == 40])} commits in history")
    print(f"# maple branches : {len(refs)} fetched refs, {len(ctimes)} commit timestamps")
    print(f"# maple PR set   : {len(maple_prs)} numbers from the research state "
          f"(minus {sorted(FOREIGN_PRS)})")
    print()

    recs = []
    for s in rows:
        m = s.get("officialMetrics") or {}
        note = s.get("note") or ""
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        cs = (MB_D / d) ** 0.75 * (MB_P / p) ** 0.25 if (d and p) else None
        f = None
        if bd and bp:
            import math
            f = 0.75 * math.log(bd / MB_D) + 0.25 * math.log(bp / MB_P)
        sig = classify(note, heads, maple_prs)
        other = OTHER_LAUNCH_RE.search(note)
        ts = ts_of(s)
        e = epoch(ts)
        near = False
        if e is not None and ctimes:
            import bisect
            i = bisect.bisect_left(ctimes, e)
            for j in (i - 1, i):
                if 0 <= j < len(ctimes) and abs(ctimes[j] - e) <= window:
                    near = True
        recs.append(dict(
            ts=ts, sha=(s.get("submissionCommitSha") or "")[:12],
            status=s.get("status"), cs=cs, f=(f * 100 if f is not None else None),
            signal=sig, other=(other.group(1).lower() if other else ""),
            near=near, note=note, note_len=len(note),
            harness=(m.get("harness_hash") or "")[:12],
        ))

    scored = [r for r in recs if r["cs"] is not None]
    print(f"## scored receipts: {len(scored)}\n")

    tally = collections.Counter(r["signal"] or "-- unattributed" for r in scored)
    print("## per-signal yield over scored receipts")
    for k in sorted(tally):
        print(f"  {k:22s} {tally[k]:4d}   {100.0 * tally[k] / len(scored):5.1f} %")
    maple_n = sum(v for k, v in tally.items() if k.startswith("S"))
    print(f"  {'MAPLE total':22s} {maple_n:4d}   {100.0 * maple_n / len(scored):5.1f} %")
    print()

    resid = [r for r in scored if not r["signal"]]
    foreign_marked = [r for r in resid if r["other"]]
    print("## residual (no maple signal)")
    print(f"  residual                : {len(resid)}")
    print(f"  ...names cedar/birch    : {len(foreign_marked)}  (positively NOT ours)")
    print(f"  ...time-adjacent to a maple branch commit (<= {a.window_min:.0f} min): "
          f"{sum(1 for r in resid if r['near'] and not r['other'])}")
    print(f"  ...neither              : "
          f"{sum(1 for r in resid if not r['near'] and not r['other'])}")
    print("  NOTE: time-adjacency is a CEILING, not an attribution.  The queue is")
    print("        shared and busy; adjacency is expected by chance alone.")
    print()

    # maple-only vs pooled dispersion --------------------------------------
    import math
    def stats(vals):
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return None
        mu = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))
        return len(vals), mu, sd

    print("## dispersion: maple-attributed vs pooled corpus")
    for label, sel in (("pooled", scored),
                       ("maple-attributed", [r for r in scored if r["signal"]]),
                       ("residual", resid)):
        st_cs = stats([100.0 * math.log(r["cs"]) for r in sel])
        st_f = stats([r["f"] for r in sel])
        if st_cs and st_f:
            print(f"  {label:18s} n={st_cs[0]:3d}  sd(100*ln cs)={st_cs[2]:.4f} %"
                  f"   mean f={st_f[1]:+.4f} %  sd(f)={st_f[2]:.4f} %")
    print()

    # duplicate-tree hunt ---------------------------------------------------
    by_sha = collections.defaultdict(list)
    for r in recs:
        if r["sha"]:
            by_sha[r["sha"]].append(r)
    dups = {k: v for k, v in by_sha.items() if len(v) > 1}
    print(f"## submissionCommitSha groups with n >= 2: {len(dups)}")
    for k, v in sorted(dups.items()):
        print(f"  {k}  n={len(v)}  " + ", ".join(
            f"{x['ts']} cs={x['cs']:.6f}" if x["cs"] else f"{x['ts']} unscored"
            for x in v))
    print()

    CAL_RE = re.compile(a.note_grep, re.I)
    hits = [r for r in recs if CAL_RE.search(r["note"])]
    print(f"## calibration / identical-tree note hits: {len(hits)}")
    for r in hits:
        snippet = " ".join(r["note"].split())[: a.snippet]
        cs = f"{r['cs']:.6f}" if r["cs"] is not None else "unscored"
        print(f"  {r['ts']}  {r['sha']}  cs={cs}  signal={r['signal'] or '--'}")
        print(f"      {snippet}")
    print()

    if a.dump_residual:
        print(f"## residual note excerpts (first {a.dump_residual}) -- read these by hand")
        for r in resid[: a.dump_residual]:
            snippet = " ".join(r["note"].split())[:220] or "(empty note)"
            print(f"  {r['ts']}  {r['sha']}  cs={r['cs']:.6f}  len={r['note_len']:5d}")
            print(f"      {snippet}")

    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(
            [{k: v for k, v in r.items() if k != "note"} for r in recs], indent=1))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
