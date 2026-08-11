#!/usr/bin/env python3
"""Turn a captured `mlxfast submissions` table into a plain TSV corpus.

Usage: python3 research/tools/extract_submission_corpus.py <raw.log> <out.tsv>
Columns: submission  status  score  commit  created
ANSI escapes are stripped; only the fields above are kept.
"""
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ROW = re.compile(r'^(\w{7})\s+(\S+)\s+(\w+)\s+([0-9.]+)\s+\{"error":"","commit":"([0-9a-f]{40})"')


def main(src, dst):
    text = ANSI.sub("", open(src, encoding="utf-8", errors="replace").read())
    out = ["#submission\tstatus\tscore\tcommit\tcreated"]
    n = 0
    for line in text.split("\n"):
        m = ROW.match(line)
        if not m:
            continue
        sub, _solver, status, score, commit = m.groups()
        created = line.split("  ")[-1].strip()
        out.append("\t".join([sub, status, score, commit, created]))
        n += 1
    open(dst, "w").write("\n".join(out) + "\n")
    print("wrote %d rows to %s" % (n, dst))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
