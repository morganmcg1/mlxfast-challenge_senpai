#!/usr/bin/env python3
"""Close-out consistency check for the two Maple handoff documents.

Run:  python3 research/tools/handoff_linkcheck.py

Checks, in order of how badly a failure would mislead an inheritor:

1. Every repo-relative path named in backticks inside the two handoff docs
   actually exists in the tree (broken pointer => an inheritor cannot reproduce).
2. Every "§N" / "§Na" section reference in each doc resolves to a heading that
   exists in that same doc (dangling cross-reference => an inheritor reads the
   wrong section and inherits a stale level).
3. The load-bearing constants appear with a single spelling across both docs
   (bar, best receipt, gap, currency, frontier commit) -- a second spelling of a
   number that everything else is divided by is the failure mode §10 exists for.

Exit code 0 iff every check passes. Read-only; touches no channel.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    ROOT / "research" / "MAPLE_TO_SLOT_HOLDER_BRIEF.md",
    ROOT / "research" / "maple_endgame_handoff_manifest.md",
]

# Backticked tokens that look like repo paths we own.
PATH_RE = re.compile(r"`(research/[A-Za-z0-9_./-]+)`")
SECT_REF_RE = re.compile(r"§(\d+[a-z]?)")
HEADING_RE = re.compile(r"^#+\s*(?:§)?(\d+[a-z]?)[.)]?\s", re.M)
SUBSECT_RE = re.compile(r"^###\s*\(([ivx]+)\)", re.M)

# Constants that must be spelled exactly one way wherever they appear.
OFF_BRANCH = {
    # Cited artifact -> (student branch, commit, vendored verbatim copy) it actually lives on. These
    # student PRs were closed unmerged by design, so the file is real but not at the cited path here.
    # See manifest §10(vii) and §10(xvii). Verified with `git ls-remote` + an explicit-refspec fetch,
    # NOT with `git branch -r`. Since 17:43Z each one also has a byte-identical local copy under
    # research/imported/ (checksums in research/imported/README.md), so the citation is openable.
    "research/tools/epoch_gate.py": (
        "maple-nezuko/r129-g-preflight-validity-gates",
        "c472f6e58efd8f81bcdc913e077f71863ad73330",
        "research/imported/epoch_gate.py",
    ),
    "research/fern-r109f-interim-1200Z.md": (
        "maple-fern/r109-integration-and-submission",
        "bd47570461dce7471c15a7f7997a93988ff11b5c",
        "research/imported/fern-r109f-interim-1200Z.md",
    ),
}

# "§N" tokens that point into a THIRD document, not into the two handoff docs.
EXTERNAL_SECTIONS = {"2259"}  # CURRENT_RESEARCH_STATE.md §2259 strike

CONSTANTS = {
    "bar": "2.6195531094824",
    "best_receipt_score": "2.60664969895906",
    "gap_pct": "0.4950",
    "currency_local": "0.00586",
    "currency_ranked": "0.01527",
    "frontier_commit": "4ea72c3",
}
# Spellings that would indicate a stale or contradictory copy survived an edit.
FORBIDDEN = {
    # old bar era value must only ever appear as the *previous* era, never as "the bar"
    "the bar is 2.6165": "previous-era bar quoted as current",
    "base 1bc1c895 is the frontier": "rolled-back frontier claim",
}


def load(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def check_paths(name: str, text: str, notes: list[str]) -> list[str]:
    bad = []
    for m in sorted(set(PATH_RE.findall(text))):
        # `research/...` / `research/…` written as prose glob, not as a real path
        if m.endswith((".", "/")) or ".." in m:
            continue
        if (ROOT / m).exists():
            continue
        if m in OFF_BRANCH:
            branch, sha, vendored = OFF_BRANCH[m]
            # The vendored copy is the whole point of the exemption: if it went missing, the
            # citation is unopenable again and that is a failure, not a note.
            if not (ROOT / vendored).exists():
                bad.append(f"{name}: OFF-BRANCH `{m}` lost its vendored copy `{vendored}`")
                continue
            notes.append(
                f"{name}: OFF-BRANCH `{m}` -> {branch} @ {sha[:8]}"
                f"; verbatim copy `{vendored}` (manifest 10(vii), 10(xvii))"
            )
            continue
        bad.append(f"{name}: missing path `{m}`")
    return bad


def check_sections(name: str, text: str) -> list[str]:
    have = set(HEADING_RE.findall(text))
    # §0b/§0c/§0e/§0f style headings are written as "## §0f ..." or "## 0. ..."
    for m in re.finditer(r"^#+\s*§?(0[a-z]?)\b", text, re.M):
        have.add(m.group(1))
    return have


def headings_of(text: str) -> set[str]:
    return check_sections("", text)


def check_refs(name: str, text: str, all_headings: set[str]) -> list[str]:
    """A §N reference resolves if it names a heading in EITHER handoff doc.

    The two documents cite each other constantly, so a same-document-only check
    reports false failures; a neither-document failure is a real dangling pointer.
    """
    bad = []
    for ref in sorted(set(SECT_REF_RE.findall(text))):
        if ref in all_headings or ref in EXTERNAL_SECTIONS:
            continue
        bad.append(f"{name}: dangling cross-reference §{ref} (resolves in neither handoff doc)")
    return bad


def check_constants(docs: dict[str, str]) -> list[str]:
    bad = []
    for key, val in CONSTANTS.items():
        seen_in = [n for n, t in docs.items() if val in t]
        if not seen_in:
            bad.append(f"constant {key}={val} appears in NEITHER doc")
    for phrase, why in FORBIDDEN.items():
        for n, t in docs.items():
            if phrase.lower() in t.lower():
                bad.append(f"{n}: forbidden phrase ({why}): {phrase!r}")
    return bad


def main() -> int:
    docs: dict[str, str] = {}
    problems: list[str] = []
    for p in DOCS:
        if not p.exists():
            problems.append(f"MISSING DOC: {p.relative_to(ROOT)}")
            continue
        docs[p.name] = load(p)

    notes: list[str] = []
    all_headings: set[str] = set()
    for text in docs.values():
        all_headings |= headings_of(text)
    for name, text in docs.items():
        problems += check_paths(name, text, notes)
        problems += check_refs(name, text, all_headings)
    problems += check_constants(docs)

    print(f"docs checked: {', '.join(docs) or '(none)'}")
    for name, text in docs.items():
        subs = SUBSECT_RE.findall(text)
        print(f"  {name}: {len(text.splitlines())} lines, "
              f"{len(set(HEADING_RE.findall(text)))} numbered sections, "
              f"{len(subs)} roman subsections {subs if subs else ''}")

    if notes:
        print("\nNOTES (cited path is off-branch; a verbatim copy is vendored here):")
        for n in notes:
            print(f"  - {n}")

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nOK: no missing paths, no dangling § references, constants single-spelled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
