#!/usr/bin/env python3
"""Gate G4 for r103-C: the relocation loses no prose and is exactly reversible.

    nezuko_r103c_relocation_verify.py ORIG STRIPPED SIDECAR

Checks, in order:

  1. line numbering is preserved (the property gate G1 depends on);
  2. the canonical literal-preserving digest is unchanged;
  3. every removed comment block appears in the sidecar verbatim and in
     source order, and the sidecar accounts for the whole removed pool;
  4. sidecar + stripped file reconstruct ORIG byte for byte.

Reconstruction reinserts each block at its recorded line span.  A block records
the blanks that separated it from the line start or from preceding code, so
appending it to the surviving line restores comment-only and trailing comments
alike.  Exit 0 only when all four checks pass.
"""

import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from nezuko_comment_tool import COMMENT, PRESERVE, digest, segments  # noqa: E402
from nezuko_relocate_tool import blocks  # noqa: E402

HEAD = re.compile(r"^## L(\d+)(?:-L(\d+))?(?: .*)?$")


def parse_sidecar(text):
    """Yield (lo, hi, chunk) for every block recorded in the sidecar."""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        m = HEAD.match(lines[i])
        if not m:
            i += 1
            continue
        lo = int(m.group(1))
        hi = int(m.group(2) or m.group(1))
        assert lines[i + 2] == "```swift", f"bad fence at L{lo}"
        j = i + 3
        while lines[j] != "```":
            j += 1
        out.append((lo, hi, "\n".join(lines[i + 3 : j])))
        i = j + 1
    return out


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    orig = open(sys.argv[1], encoding="utf-8").read()
    strip = open(sys.argv[2], encoding="utf-8").read()
    side = open(sys.argv[3], encoding="utf-8").read()
    ok = True

    if orig.count("\n") == strip.count("\n"):
        print(f"1. line numbering preserved: PASS ({orig.count(chr(10))} lines)")
    else:
        print(f"1. line numbering: FAIL {orig.count(chr(10))} -> {strip.count(chr(10))}")
        ok = False

    if digest(orig, "swift") == digest(strip, "swift"):
        print(f"2. canonical digest unchanged: PASS ({digest(orig, 'swift')[:16]})")
    else:
        print("2. canonical digest: FAIL")
        ok = False

    spans = blocks(orig, "swift")
    recorded = parse_sidecar(side)
    pool = sum(len(orig[a:b].encode()) for a, b in spans)
    if len(recorded) == len(spans):
        print(f"3a. block count: PASS ({len(spans)})")
    else:
        print(f"3a. block count: FAIL {len(spans)} removed vs {len(recorded)} recorded")
        ok = False
    mismatch = [
        i
        for i, ((a, b), (_, _, chunk)) in enumerate(zip(spans, recorded))
        if orig[a:b].rstrip("\n") != chunk
    ]
    if mismatch:
        print(f"3b. verbatim prose: FAIL at block {mismatch[0]}")
        ok = False
    else:
        print(f"3b. verbatim prose in source order: PASS ({pool} bytes of pool)")

    # 4. Rebuild ORIG from the stripped file plus the sidecar.
    out = strip.split("\n")
    for lo, hi, chunk in recorded:
        body = chunk.split("\n")
        assert hi - lo + 1 == len(body), f"span/length mismatch at L{lo}"
        for k, line in enumerate(body):
            out[lo - 1 + k] += line
    rebuilt = "\n".join(out)
    if rebuilt == orig:
        print("4. reconstruction: PASS (byte-identical to original)")
    else:
        first = next(
            (i for i in range(min(len(rebuilt), len(orig))) if rebuilt[i] != orig[i]),
            min(len(rebuilt), len(orig)),
        )
        print(f"4. reconstruction: FAIL, first difference at byte {first}")
        print(f"   orig: {orig[max(0, first - 60):first + 60]!r}")
        print(f"   back: {rebuilt[max(0, first - 60):first + 60]!r}")
        ok = False

    print("G4 PASS" if ok else "G4 FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
