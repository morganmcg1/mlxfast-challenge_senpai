#!/usr/bin/env python3
"""Analyse which file-scope declarations cross a proposed carve boundary.

Usage: fern_split_analysis.py FILE START_LINE END_LINE
Reports file-scope declarations whose visibility must widen for the carve,
and any type in the carve region that has extensions outside it.
"""
import re
import sys
from collections import defaultdict

path, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
lines = open(path).read().split("\n")

DECL = re.compile(
    r"^(?P<mods>(?:@\w+(?:\([^)]*\))?\s+)*)"
    r"(?P<vis>public |internal |private |fileprivate )?"
    r"(?P<kw>final class |class |struct |enum |protocol |extension |func |let |var |actor )"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)

decls = []  # (line_no(1-based), vis, kw, name)
for i, line in enumerate(lines, 1):
    if not line or line[0] in " \t}/":
        continue
    m = DECL.match(line)
    if m:
        decls.append((i, (m.group("vis") or "internal ").strip(), m.group("kw").strip(), m.group("name")))

# usages by name
usage = defaultdict(list)
names = {d[3] for d in decls}
tok = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
for i, line in enumerate(lines, 1):
    for t in set(tok.findall(line)):
        if t in names:
            usage[t].append(i)


def in_carve(n):
    return start <= n <= end


def decl_span(idx):
    """Approximate declaration span: from its line to line before next file-scope decl."""
    ln = decls[idx][0]
    nxt = decls[idx + 1][0] if idx + 1 < len(decls) else len(lines) + 1
    return ln, nxt - 1


print(f"carve {start}-{end} of {path} ({len(lines)} lines)")
print()
must_widen_out = []  # declared in carve, used outside
must_widen_in = []   # declared outside carve, used inside
for idx, (ln, vis, kw, name) in enumerate(decls):
    if vis not in ("private", "fileprivate"):
        continue
    s, e = decl_span(idx)
    uses = [u for u in usage[name] if not (s <= u <= e)]
    if in_carve(ln):
        outside = [u for u in uses if not in_carve(u)]
        if outside:
            must_widen_out.append((ln, kw, name, outside[:6], len(outside)))
    else:
        inside = [u for u in uses if in_carve(u)]
        if inside:
            must_widen_in.append((ln, kw, name, inside[:6], len(inside)))

print(f"== private decls INSIDE carve used OUTSIDE ({len(must_widen_out)}) ==")
for ln, kw, name, u, n in must_widen_out:
    print(f"  {ln:>6} {kw:<12} {name}  uses={n} e.g. {u}")
print()
print(f"== private decls OUTSIDE carve used INSIDE ({len(must_widen_in)}) ==")
for ln, kw, name, u, n in must_widen_in:
    print(f"  {ln:>6} {kw:<12} {name}  uses={n} e.g. {u}")
print()

# extensions of carve types living outside the carve
carve_types = {name for ln, vis, kw, name in decls if in_carve(ln) and kw in ("class", "final class", "struct", "enum", "actor", "protocol")}
ext_out = [(ln, name) for ln, vis, kw, name in decls if kw == "extension" and name in carve_types and not in_carve(ln)]
print(f"== extensions of carve types outside carve ({len(ext_out)}) ==")
for ln, name in ext_out:
    print(f"  {ln:>6} extension {name}")

# private members of carve types referenced from outside the carve region
print()
print("== carve region top-level decl inventory ==")
for ln, vis, kw, name in decls:
    if in_carve(ln):
        print(f"  {ln:>6} {vis:<11} {kw:<12} {name}")
