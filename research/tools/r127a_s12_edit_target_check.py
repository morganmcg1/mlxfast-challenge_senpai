#!/usr/bin/env python3
"""R127-A §12 — verify every recommended-edit target still exists, at the exact line
the work order cites, in the advisor branch head this audit read.

Read-only: shells out to `git show <sha>:<path>` and does string containment checks.
No GPU, no build, no benchmark, no network.

Usage:  python3 research/tools/r127a_s12_edit_target_check.py
Exit 0 iff all targets are present at their cited line.
"""
import subprocess
import sys

SHA = "6778867dc8579eff3302d49d064c2bc0cf60ead2"  # codex/mlxfast-maple-20260804-advisor @ 12:59Z
MAN = "research/maple_endgame_handoff_manifest.md"
CRS = "research/CURRENT_RESEARCH_STATE.md"
TOOL = "research/tools/slot_holder_arithmetic.py"

# (work-order id, path, line at SHA, verbatim substring that must be on that line)
TARGETS = [
    ("A1  6.1  currency table", MAN, 999, "| currency | decode step | 1 \u00b5s/step is | provenance |"),
    ("A2  6.2  consequence (a)", MAN, 1008, "cannot be sourced"),
    ("A3  6.3  requirement table", MAN, 1029, "local-submit \u00b5s/step (8882"),
    ("A4  8.1  '~40 % too high'", MAN, 1035, 'The old table\'s "44 / 84" column'),
    ("A5  6.4  \u00a76.6 closing", MAN, 1041, "frieren's +55.2 \u00b5s/step FUSED"),
    ("A6  6.5  \u00a77-item-2 reprice", MAN, 1048, "\u22488919 \u00b5s wall vs \u22488567 \u00b5s busy"),
    ("A7  6.6  rule for reuse", MAN, 1054, "Rule for reuse: never write a \u00b5s/step number"),
    ("A8  8.1  F1 copy in \u00a76.5", MAN, 819, "originally read \u224844 and \u224884 \u00b5s/step"),
    ("A9  6.7  o_proj \u221282", MAN, 466, "%-of-measured-peak"),
    ("A10 6.8  #731 units (\u00a74)", MAN, 241, "\u22120.282 % of score"),
    ("A11 6.8  #731 units (\u00a75)", MAN, 481, "\u22120.282 % score"),
    ("A12 6.9  routed/shared (\u00a74c)", MAN, 416, "edward's routed-wall replica"),
    ("A13 6.9  \u00a74a/\u00a74b banner clause", MAN, 258, "on edward's routed-wall measurement (#731)"),
    ("A14 6.10 \u00a74b \u22120.03 % cell", MAN, 321, "\u2248 \u22120.03 % of score or worse"),
    ("A15 6.11 delta 2 (\u00a74)", MAN, 239, "routed expert down-GEMM"),
    ("A16 6.11 delta 2 (\u00a75)", MAN, 503, "\u2248+0.04 % score"),
    ("A17 6.12 operating point", MAN, 157, "Operating point: S = 97.863 ms"),
    ("A18 8.3  \u00a76.5c \u22480 % row", MAN, 954, "within-program \u03c3 0.1860\u20130.2276 %"),
    ("A19 11.4 leakage sentence", MAN, 908, "leakage that program-hashing removes"),
    ("A20 10.4 retired crown", CRS, 3412, "Record still **2.61650354381456**"),
    ("A21 10.4 P(record) table", CRS, 3511, "variance is the `bl_pre` baseline draw"),
    ("A22 11.4 undated median draw", CRS, 3509, "median 0.998597, sd(ln L) 0.5359 %"),
    ("A23 10.4 tool: need is a draw factor", TOOL, 35, "need = BAR / OUR_PROGRAM"),
    ("A24 10.4 tool: wrong \u03c3, wrong centre", TOOL, 37, "z = (need - DRAW_MEDIAN) / DRAW_SD"),
    ("A25 9.3  \u00a76.5b self-cited", MAN, 872, "6.5b Independent confirmation"),
]


def read(path):
    out = subprocess.run(["git", "show", f"{SHA}:{path}"], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"cannot read {SHA}:{path} -- {out.stderr.strip()}")
    return out.stdout.split("\n")


def main():
    cache = {}
    bad = 0
    print(f"advisor head {SHA}")
    for tid, path, line, anchor in TARGETS:
        body = cache.setdefault(path, read(path))
        got = body[line - 1] if 0 < line <= len(body) else ""
        ok = anchor in got
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {tid:<38} {path.split('/')[-1]}:{line}")
        if not ok:
            print(f"        want {anchor!r}\n        got  {got[:120]!r}")
    print(f"{len(TARGETS) - bad}/{len(TARGETS)} edit targets present at the cited line")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
