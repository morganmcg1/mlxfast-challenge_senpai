"""Extract the last senpai-result:v1 summary for a given PR from a get_prs artifact.

Usage:
    python3 research/tools/extract_results.py <pr_number> [summary_char_limit]

Input resolution:
    1. $MAPLE_PR_ARTIFACT                      (explicit override; a file or a dir)
    2. ./pull-requests-*.md                    (artifact copied next to the checkout)
    3. <role>/state/openhands_state/github/pull-requests-*.md, located *relative to
       this file* (checkout lives at <role>/workspace/target), plus sibling roles.
       Do NOT use ~: the role HOME is sandboxed to <role>/home and does not contain
       the state tree -- that mistake silently returns "no artifact".
    Among all matches the NEWEST by mtime wins, and its mtime is printed as the
    freshness bound on the answer.

IMPORTANT (see manifest rule 23): the get_prs artifact is a *host-local cache*, not
part of the repository.  An inheritor on a different machine will not have it, and a
stale copy is not evidence about the live PR set.  If this tool reports "no artifact",
that is a missing index, NOT a statement that the PR has no results -- re-run get_prs
and point $MAPLE_PR_ARTIFACT at the fresh file.
"""
import datetime
import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # research/tools
_REPO = os.path.dirname(os.path.dirname(_HERE))              # checkout root
_ROLE = os.path.dirname(os.path.dirname(_REPO))              # <role>
_ROLES = os.path.dirname(_ROLE)                              # roles/

STATE_GLOBS = [
    os.path.join(_ROLE, "state/openhands_state/github/pull-requests-*.md"),
    os.path.join(_ROLES, "*/state/openhands_state/github/pull-requests-*.md"),
]


def candidates():
    """Every plausible artifact path, unfiltered."""
    env = os.environ.get("MAPLE_PR_ARTIFACT")
    if env:
        if os.path.isdir(env):
            for p in glob.glob(os.path.join(env, "pull-requests-*.md")):
                yield p
        else:
            yield env
    for p in glob.glob("pull-requests-*.md"):
        yield p
    for g in STATE_GLOBS:
        for p in glob.glob(g):
            yield p


def stamp_of(path):
    return datetime.datetime.fromtimestamp(
        os.path.getmtime(path), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def blocks_for(path, want):
    """senpai-result:v1 payloads in `path` belonging to PR `want`."""
    try:
        text = open(path, errors="replace").read()
    except OSError:
        return []
    out = []
    for b in re.findall(r"<!-- senpai-result:v1 (\{.*?\}) -->", text, re.S):
        try:
            d = json.loads(b)
            pr = str(d["assignment"]["pr_number"])
        except Exception:
            continue
        if pr == want:
            out.append(d)
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    want = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3000

    files = sorted({p for p in candidates() if os.path.isfile(p)},
                   key=os.path.getmtime, reverse=True)
    if not files:
        print("no artifact: no get_prs pull-requests-*.md found via "
              "$MAPLE_PR_ARTIFACT, ./, or the role state dir.")
        print("This is a MISSING INDEX, not an absence of results (manifest rule 23).")
        return 3

    print("scanned %d artifact(s); newest %s (%s)"
          % (len(files), os.path.basename(files[0]), stamp_of(files[0])))

    # Newest artifact that actually contains this PR wins.
    for path in files:
        hits = blocks_for(path, want)
        if hits:
            break
    else:
        print("PR #%s: 0 result block(s) in any of the %d artifact(s) scanned."
              % (want, len(files)))
        print("MISSING INDEX, not proven absence (rule 23): these artifacts only "
              "cover the PRs the get_prs calls that wrote them happened to request. "
              "Re-run get_prs for this PR before concluding anything.")
        return 4

    print("artifact: " + path)
    print("artifact last written (UTC): " + stamp_of(path)
          + "  <- freshness bound on every claim below")
    print("PR #%s: %d result block(s) in this artifact" % (want, len(hits)))
    for d in hits[-1:]:
        print("status:", d.get("status"), " commit:", d.get("commit_sha"))
        print("metric:", json.dumps(d.get("primary_metric")))
        print("runs:", [r.get("run_id") for r in d.get("runs", [])])
        print("---SUMMARY---")
        print(d.get("summary", "")[:limit])
    return 0


if __name__ == "__main__":
    sys.exit(main())
