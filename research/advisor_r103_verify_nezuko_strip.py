#!/usr/bin/env python3
"""Independent rule-74 check on nezuko's #575 LRM comment strip.

Her gate is compiler-as-oracle (MLXFastModel.o sha256 identity across four
interleaved forced-clean builds).  This is a *different* instrument aimed at the
same hazard: locate every multi-line Swift string literal (\"\"\" ... \"\"\") in the
ORIGINAL file -- that is where the embedded MSL kernel source lives -- and prove
that no changed line falls inside one.  If any did, a `//` that is really Metal
source could have been deleted.
"""
import subprocess
import sys

BASE = "0f6862d099252d40a807df30abfbbd7c9cd596ae"
CAND = "52bbb0e9611117eef7a4e865036341cb350eb100"
PATH = "Sources/MLXFastModel/LagunaRuntimeModel.swift"


def show(rev):
    out = subprocess.run(["git", "show", f"{rev}:{PATH}"],
                         capture_output=True, check=True).stdout
    return out.decode("utf-8").split("\n")


a = show(BASE)
b = show(CAND)
print(f"base lines={len(a)}  cand lines={len(b)}")
if len(a) != len(b):
    print("FAIL: line counts differ; the line-preservation claim is false")
    sys.exit(1)

# Map multi-line string literal regions in the ORIGINAL.
inside = [False] * len(a)
depth = 0
for i, line in enumerate(a):
    n = line.count('"""')
    if depth:
        inside[i] = True
    for _ in range(n):
        depth ^= 1
        if depth:
            inside[i] = True   # opening line itself
        else:
            inside[i] = True   # closing line itself
lit_lines = sum(inside)
print(f'lines inside \"\"\" literals: {lit_lines} '
      f"({100.0*lit_lines/len(a):.1f}% of the file)")

changed = [i for i in range(len(a)) if a[i] != b[i]]
print(f"changed lines: {len(changed)}")
bad = [i for i in changed if inside[i]]
print(f"changed lines INSIDE a multi-line literal: {len(bad)}")
if bad:
    for i in bad[:20]:
        print(f"  !! line {i+1}\n     - {a[i][:120]}\n     + {b[i][:120]}")

# Characterise what the changed lines actually were.
emptied = sum(1 for i in changed if b[i].strip() == "")
comment_only = sum(1 for i in changed
                   if a[i].lstrip().startswith("//") and b[i].strip() == "")
trailing = len(changed) - comment_only - (emptied - comment_only)
print(f"  of which: whole-line // comments emptied to '' : {comment_only}")
print(f"            any change whose result is blank      : {emptied}")
print(f"            changes leaving non-blank text        : "
      f"{len(changed) - emptied}")

others = [i for i in changed if b[i].strip() != ""]
for i in others[:15]:
    print(f"     line {i+1}\n       - {a[i][:140]}\n       + {b[i][:140]}")

# Bytes.
ba = sum(len(x.encode()) + 1 for x in a)
bb = sum(len(x.encode()) + 1 for x in b)
print(f"\nbytes: {ba} -> {bb}   freed {ba-bb}")

# Non-comment payload must be byte-identical.
def payload(lines):
    return "\n".join(x for x in lines if x.strip() != "")


pa, pb = payload(a), payload(b)
print(f"non-blank payload identical: {pa == pb}")
if pa != pb:
    la = [x for x in a if x.strip() != ""]
    lb = [x for x in b if x.strip() != ""]
    print(f"  non-blank counts {len(la)} vs {len(lb)}")

print("\nVERDICT:", "PASS" if not bad else "FAIL")
