#!/usr/bin/env python3
"""Archive the submission-poller logs that are §7.4's only raw input.

Why this exists
---------------
§7.4 of ``research/maple-fern-r109f-instrument-collapse.md`` derives every exact
service bracket in the campaign from the logs written by
``research/fern_r109f_submit_when_free.py``.  Those logs live in the *runtime's*
job-log directory, which is outside the git checkout: a reviewer who clones the
branch sees the section's conclusions and none of its evidence.  That is exactly
the "trust me, I ran it" shape the rest of this campaign refuses to accept from
anybody else, so it should not be accepted here either.

This tool copies the poller logs into
``research/artifacts/fern-r109f/pollerlogs/`` under stable, meaningful names and
writes a manifest with byte counts and line counts, so
``fern_r109f_poller_occupancy.py --glob 'research/artifacts/fern-r109f/pollerlogs/*.log'``
reproduces §7.4(a)-(d) and §7.4(h) offline from committed files.

Selection rule
--------------
A log is a poller log iff it contains at least one ``slot BUSY``/``slot FREE``
line.  Nothing else is copied: the job-log directory also holds build logs and
W&B publication logs, which are large, uninteresting here, and in a couple of
cases contain the full text of submission notes.

Redaction
---------
Poller logs are already free of credentials -- the poller never echoes the
bearer token -- but the check is cheap and a leaked token would be expensive, so
every copied line is scanned for the token shapes that could appear and the run
aborts loudly rather than committing a secret.

Usage
-----
    python3 research/fern_r109f_archive_poller_logs.py [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEST = os.path.join(HERE, "artifacts", "fern-r109f", "pollerlogs")

# $HOME here is the ROLE's home (.../roles/student-maple-fern/home), so the
# state directory is its sibling, not a child.  Getting this wrong silently
# finds zero logs, which is why it is written once, here.
LOGDIR = os.path.join(
    os.path.dirname(os.path.expanduser("~")),
    "state",
    "openhands_state",
    "training",
)

SLOT_RE = re.compile(r"slot (?:BUSY|FREE)")

# Shapes that must never reach a committed file.  The MLXFast token and the W&B
# key are both long opaque strings; a bearer header would be the giveaway.
SECRET_RE = re.compile(
    r"(?:Bearer\s+\S{16,})"
    r"|(?:MLXFAST_API_TOKEN\s*=\s*\S+)"
    r"|(?:WANDB_API_KEY\s*=\s*\S+)"
    r"|(?:\b[0-9a-f]{40}\b(?=\s*$))",  # bare 40-hex on its own == wandb key shape
)

# A bare 40-hex string is also what a git sha looks like, and poller logs DO
# print package shas.  So the secret scan below only treats a 40-hex token as
# suspicious when the line does not look like it is talking about a commit.
SHA_CONTEXT_RE = re.compile(
    r"sha|commit|package|pkg|base|HEAD|tag", re.IGNORECASE
)


def classify(path: str, text: str) -> str:
    """Give the archived copy a name a reader can reason about."""
    job = os.path.basename(path)[:8]
    n_submitted = text.count("-> submitting")
    n_busy = text.count("slot BUSY")
    if "max-wait exceeded" in text:
        kind = "expired"
    elif n_submitted:
        kind = "submitted"
    elif n_busy:
        kind = "watching"
    else:
        kind = "other"
    return "poller-%s-%s.log" % (job, kind)


def scan_secrets(text: str) -> list[str]:
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        m = SECRET_RE.search(line)
        if not m:
            continue
        hit = m.group(0)
        # 40-hex alone is a sha in this codebase's logs; only flag it if the
        # line gives no commit-ish context.
        if re.fullmatch(r"[0-9a-f]{40}", hit) and SHA_CONTEXT_RE.search(line):
            continue
        bad.append("line %d: %s" % (i, hit[:24] + "..."))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--logdir", default=LOGDIR)
    args = ap.parse_args()

    if not os.path.isdir(args.logdir):
        print("no log dir: %s" % args.logdir)
        return 1

    found = []
    for p in sorted(glob.glob(os.path.join(args.logdir, "*.log"))):
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if not SLOT_RE.search(text):
            continue
        found.append((p, text))

    print("poller logs found: %d (of %d job logs)"
          % (found.__len__(), len(glob.glob(os.path.join(args.logdir, "*.log")))))

    failures = 0
    rows = []
    for p, text in found:
        secrets = scan_secrets(text)
        if secrets:
            failures += 1
            print("  REFUSING %s -- possible secret:" % os.path.basename(p))
            for s in secrets[:3]:
                print("    %s" % s)
            continue
        name = classify(p, text)
        rows.append(
            {
                "path": p,
                "src": os.path.basename(p),
                "dest": name,
                "bytes": len(text),
                "lines": text.count("\n") + 1,
                "busy": text.count("slot BUSY"),
                "free": text.count("slot FREE"),
                "submitted": text.count("-> submitting"),
            }
        )

    if failures:
        print("aborting: %d log(s) failed the secret scan" % failures)
        return 1

    rows.sort(key=lambda r: -r["bytes"])
    print()
    print("%-40s %8s %6s %6s %5s %4s" % ("dest", "bytes", "lines", "busy", "free", "sub"))
    for r in rows:
        print(
            "%-40s %8d %6d %6d %5d %4d"
            % (r["dest"], r["bytes"], r["lines"], r["busy"], r["free"], r["submitted"])
        )
    total = sum(r["bytes"] for r in rows)
    print("total %d bytes across %d files" % (total, len(rows)))

    if args.dry_run:
        print("(dry run: nothing written)")
        return 0

    os.makedirs(DEST, exist_ok=True)
    for r in rows:
        shutil.copyfile(r["path"], os.path.join(DEST, r["dest"]))

    man = os.path.join(DEST, "MANIFEST.txt")
    with open(man, "w", encoding="utf-8") as fh:
        fh.write(
            "Submission-poller logs archived from the runtime job-log directory.\n"
            "These are the raw input to section 7.4 of\n"
            "research/maple-fern-r109f-instrument-collapse.md (exact service\n"
            "brackets, slot occupancy, and the 7.4(h) queue-ownership split).\n"
            "\n"
            "Reproduce section 7.4 offline:\n"
            "  python3 research/fern_r109f_poller_occupancy.py \\\n"
            "      --glob 'research/artifacts/fern-r109f/pollerlogs/*.log'\n"
            "\n"
            "Names encode the job id prefix and the outcome:\n"
            "  submitted = the poller won a free slot and fired a submission\n"
            "  expired   = --max-wait elapsed with the slot still busy\n"
            "  watching  = the poller was still running, or was terminated,\n"
            "              while the slot was occupied\n"
            "\n"
            "%-40s %8s %6s %6s %5s %4s  %s\n"
            % ("dest", "bytes", "lines", "busy", "free", "sub", "source job log")
        )
        for r in rows:
            fh.write(
                "%-40s %8d %6d %6d %5d %4d  %s\n"
                % (
                    r["dest"],
                    r["bytes"],
                    r["lines"],
                    r["busy"],
                    r["free"],
                    r["submitted"],
                    r["src"],
                )
            )
        fh.write("\ntotal %d bytes across %d files\n" % (total, len(rows)))
    print("wrote %s and %d logs" % (man, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
