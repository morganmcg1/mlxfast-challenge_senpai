#!/usr/bin/env python3
"""Rule 105.15 — mechanical re-verification of what the correctness instrument
actually measures.

Origin: maple-fern, R106-J section 4.1 (self-retraction). Verified at source by
the advisor before propagation, and narrowed: the *gate* is real even though the
two fields the campaign has been quoting are not.

Three assertions, each re-checkable from the tree with no build and no run:

  A. `max_abs_diff` is a hard-coded literal 0 at every harness emit site.
     => it is a schema constant, not a measurement. Never cite it.

  B. `golden_hash` is `golden.sha256`, the digest of the LOADED FIXTURE.
     => it identifies which input file was read, not that outputs agreed.

  C. The correctness gate itself compares exact token IDs with no tolerance.
     => `passed_correctness` / `checked_steps` / `first_failing_step` are
        genuine evidence of TOKEN-IDENTITY ON ONE FIXTURE, and nothing more.

Consequence (105.15(d)): in this campaign "bit-exact" has only ever been
evidenced as "token-identical on the local golden fixture". Any transformation
that reorders floating-point accumulation is NOT numerically bit-exact merely
because it ran green, and rule 102's margin-certificate requirement is
strengthened rather than satisfied by a green run.

Usage:  python3 research/advisor_r105_15_correctness_instrument.py [repo_root]
Exit 0 if all three assertions hold on the tree, 1 otherwise.
"""

from __future__ import annotations

import pathlib
import re
import sys

# (path, what we expect to find, why it matters)
LITERAL_SITES = [
    "Sources/MLXFastHarness/LagunaRuntimeBenchmark.swift",
    "Sources/MLXFastHarness/LagunaRuntimeLocalIterate.swift",
    "Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift",
    "Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift",
    "Sources/MLXFastCore/Score.swift",
]
GOLDEN_HASH_SITE = "Sources/MLXFastTrustedHarness/LagunaRuntimeCorrectness.swift"
COMPARE_SITE = "Sources/MLXFastCore/Golden.swift"

# `maxAbsDiff: <expr>` where <expr> is anything other than the literal 0 would
# mean the field is computed somewhere and the retraction is wrong.
ASSIGN_RE = re.compile(r"maxAbsDiff\s*:\s*([^,\n)]+)")
GOLDEN_RE = re.compile(r"goldenHash\s*:\s*([^,\n)]+)")
TOKEN_CMP_RE = re.compile(r"expectedToken\s*!=\s*actualToken")
# Any numeric tolerance in the comparison path would soften "exact".
TOLERANCE_RE = re.compile(r"\b(tolerance|atol|rtol|epsilon|approximatelyEqual)\b",
                          re.IGNORECASE)


def read(root: pathlib.Path, rel: str) -> str | None:
    p = root / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1] if len(argv) > 1 else ".").resolve()
    failures: list[str] = []

    # ---- A -----------------------------------------------------------------
    # Forms that merely copy or re-round the already-constant value. These are
    # not computations: `r()` is the rounding helper used by Score.rounded().
    PASSTHROUGH = {"maxAbsDiff", "r(maxAbsDiff", "self.maxAbsDiff"}
    computed: list[str] = []
    literals = 0
    passthrough = 0
    for rel in LITERAL_SITES:
        text = read(root, rel)
        if text is None:
            failures.append(f"A: missing file {rel}")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            m = ASSIGN_RE.search(line)
            if not m:
                continue
            rhs = m.group(1).strip()
            if rhs == "0":
                literals += 1
            elif rhs in ("Double", "Double,"):  # declaration in the initialiser
                continue
            elif rhs in PASSTHROUGH:
                passthrough += 1
            else:
                computed.append(f"{rel}:{lineno}  maxAbsDiff: {rhs}")
    print(f"[A] max_abs_diff literal-0 assignments found: {literals}; "
          f"pass-through copies: {passthrough}")
    if computed:
        print("[A] ⚠ assignments that are NOT the literal 0:")
        for c in computed:
            print(f"      {c}")
        failures.append("A: max_abs_diff is computed somewhere; retraction is wrong")
    elif literals == 0:
        failures.append("A: no maxAbsDiff assignments found at all")
    else:
        print("[A] ✅ max_abs_diff is a hard-coded constant at every emit site. "
              "It is NOT a measurement. Never cite it.")

    # ---- B -----------------------------------------------------------------
    text = read(root, GOLDEN_HASH_SITE)
    if text is None:
        failures.append(f"B: missing file {GOLDEN_HASH_SITE}")
    else:
        rhs_values = [m.group(1).strip() for m in GOLDEN_RE.finditer(text)]
        from_fixture = [r for r in rhs_values
                        if "sha256" in r and ("golden" in r.lower())]
        print(f"[B] goldenHash assignments: {len(rhs_values)}; "
              f"sourced from the loaded fixture digest: {len(from_fixture)}")
        others = [r for r in rhs_values if r not in from_fixture
                  and r not in ("String", "goldenHash", '""')]
        if others:
            print("[B] ⚠ goldenHash sourced from something else:")
            for o in sorted(set(others)):
                print(f"      {o}")
        if not from_fixture:
            failures.append("B: goldenHash is not the fixture digest")
        else:
            print("[B] ✅ golden_hash is the digest of the LOADED FIXTURE. Two runs "
                  "sharing it read the same input; it says nothing about outputs.")

    # ---- C -----------------------------------------------------------------
    text = read(root, COMPARE_SITE)
    if text is None:
        failures.append(f"C: missing file {COMPARE_SITE}")
    else:
        hits = [lineno for lineno, line in enumerate(text.splitlines(), 1)
                if TOKEN_CMP_RE.search(line)]
        tol = [lineno for lineno, line in enumerate(text.splitlines(), 1)
               if TOLERANCE_RE.search(line)]
        print(f"[C] exact token-ID comparisons at lines: {hits}")
        print(f"[C] tolerance-like identifiers in the comparison path: "
              f"{tol if tol else 'none'}")
        if not hits:
            failures.append("C: no exact token comparison found; the gate is not "
                            "what 105.15(c) says it is")
        else:
            print("[C] ✅ the gate compares exact token IDs with no tolerance. "
                  "A green run IS evidence — of token-identity on ONE fixture.")

    # ---- verdict -----------------------------------------------------------
    print()
    if failures:
        print("RULE 105.15 CHECK FAILED — the tree no longer matches the finding:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RULE 105.15 verified on this tree.")
    print('  "bit-exact" in this campaign == "token-identical on the local golden '
          'fixture".')
    print("  Accumulation-reordering changes (cross-lane reduction packing, "
          "split-K, tile")
    print("  regrouping, unroll depth, threadgroup repartitioning) are NOT "
          "numerically")
    print("  bit-exact merely because they ran green. Rule 102's margin "
          "certificate is")
    print("  STRENGTHENED by this, not satisfied by it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
