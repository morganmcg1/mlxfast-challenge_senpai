#!/usr/bin/env python3
"""Per-BUFFER device load/store census over `metal -S -emit-llvm` output.

The existing censuses (`research/tanjiro_ir_census_lib.py:22-44`,
`research/maple-alphonse-r107c-air-census.py:14-32`) bucket accesses by address
space only. R107-F's arithmetic claim is per-operand -- "32 B of activation, 32 B
of codes, 4 B of scale per lane per call" -- so it needs each `addrspace(1)`
access attributed to the kernel argument it came from, and its access WIDTH.

Method: build a def->def map inside one function body, then walk each load's or
store's pointer operand backwards through the pointer-producing opcodes
(`getelementptr`, `bitcast`, `addrspacecast`, `inttoptr`, `select`, `phi`) until
a named function argument is reached. A `phi`/`select` that reaches two different
arguments is reported as ambiguous rather than silently attributed.

Width is taken from the loaded/stored value type, so a vectorised
`<4 x bfloat>` load counts as one access of 8 B and the vectoriser cannot hide
behind a scalar count.

Usage:
    maple_frieren_r107f_buffer_census.py FILE.ll [--json OUT] [--filter SUBSTR]
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict

FUNC_RE = re.compile(r"^define\s+.*?@([\w$.]+)\((.*)$")
DEF_RE = re.compile(r"^\s*(%[\w.]+)\s*=\s*(.*)$")
ARG_RE = re.compile(r"(%[\w.]+)\s*(?:,|\)|$)")

# Scalar/vector type -> bytes.
PRIM = {
    "i8": 1, "i16": 2, "i32": 4, "i64": 8, "i1": 1,
    "half": 2, "bfloat": 2, "float": 4, "double": 8,
}
VEC_RE = re.compile(r"<(\d+)\s*x\s*([\w]+)>")

PTR_OPS = ("getelementptr", "bitcast", "addrspacecast", "inttoptr", "select", "phi")


def type_bytes(ty):
    ty = ty.strip()
    m = VEC_RE.match(ty)
    if m:
        n = int(m.group(1))
        base = PRIM.get(m.group(2))
        return n * base if base else None
    return PRIM.get(ty)


def operands(rhs):
    """SSA values referenced on the right-hand side, in order."""
    return re.findall(r"%[\w.]+", rhs)


def parse_signature(sig_tail, lines, idx):
    """Collect the argument list, which `metal -S` may wrap over lines."""
    buf = sig_tail
    j = idx
    while "{" not in buf and j + 1 < len(lines):
        j += 1
        buf += " " + lines[j].strip()
    args = []
    depth = 0
    cur = ""
    body = buf[: buf.find("{")] if "{" in buf else buf
    body = body[: body.rfind(")")] if ")" in body else body
    for ch in body:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur)
    out = []
    for a in args:
        names = re.findall(r"%[\w.]+", a)
        out.append(names[-1] if names else None)
    return out, j


def census_function(name, arg_names, body):
    defs = {}
    for ln in body:
        m = DEF_RE.match(ln)
        if m:
            defs[m.group(1)] = m.group(2)

    argset = set(a for a in arg_names if a)
    memo = {}

    def origin(val, depth=0):
        if val in argset:
            return val
        if val in memo:
            return memo[val]
        if depth > 64 or val not in defs:
            return "<unknown>"
        memo[val] = "<cycle>"
        rhs = defs[val]
        op = rhs.split()[0] if rhs.split() else ""
        if not any(rhs.startswith(p) or f" {p} " in rhs[:24] for p in PTR_OPS) \
                and op not in PTR_OPS:
            memo[val] = "<unknown>"
            return memo[val]
        found = set()
        for o in operands(rhs):
            if o == val:
                continue
            r = origin(o, depth + 1)
            if r not in ("<unknown>", "<cycle>"):
                found.add(r)
        if len(found) == 1:
            memo[val] = next(iter(found))
        elif len(found) > 1:
            memo[val] = "<ambiguous:" + "|".join(sorted(found)) + ">"
        else:
            memo[val] = "<unknown>"
        return memo[val]

    counts = defaultdict(Counter)   # buffer -> {"loads":n,"load_bytes":n,...}
    addrspace = Counter()
    other = Counter()
    labels = set()
    branch_targets = []
    for ln in body:
        s = ln.strip()
        lm = re.match(r"^([\w.]+):", s)
        if lm:
            labels.add(lm.group(1))
        for t in re.findall(r"label %([\w.]+)", s):
            branch_targets.append((t, len(labels)))
        m = re.match(r"(?:%[\w.]+\s*=\s*)?(?:tail\s+)?(load|store)\s+(.*)$", s)
        if not m:
            if "air.wg.barrier" in s or "air.simdgroup.barrier" in s:
                other["barrier"] += 1
            continue
        kind, rest = m.group(1), m.group(2)
        asm = re.search(r"addrspace\((\d+)\)", rest)
        space = int(asm.group(1)) if asm else 0
        addrspace[f"{kind}_as{space}"] += 1
        if space != 1:
            continue
        # Typed-pointer AIR: `load <4 x bfloat>, <4 x bfloat> addrspace(1)* %11`
        # and `store <2 x i32> %v, <2 x i32> addrspace(1)* %p`.
        mm = re.search(r"addrspace\(1\)\s*\*?\s*(%[\w.]+)", rest)
        ptr = mm.group(1) if mm else None
        if kind == "load":
            ty = rest.split(",")[0].strip()
        else:
            ty = rest.split()[0]
        if ptr is None:
            other[f"{kind}_unattributed"] += 1
            continue
        buf = origin(ptr)
        nb = type_bytes(ty)
        counts[buf][f"{kind}s"] += 1
        counts[buf][f"{kind}_bytes"] += nb if nb else 0
        if nb is None:
            counts[buf][f"{kind}_unsized"] += 1
        counts[buf][f"{kind}_w{nb}"] += 1
    # A back edge means the counts below are per-iteration, not per-thread: the
    # trip count has to come from the source. Report it rather than hide it.
    back_edges = sum(1 for t, seen in branch_targets if t in labels and seen > 0)
    return {
        "function": name,
        "args": arg_names,
        "basic_blocks": len(labels),
        "back_edges": back_edges,
        "fully_unrolled": back_edges == 0,
        "addrspace_totals": dict(addrspace),
        "other": dict(other),
        "per_buffer": {k: dict(v) for k, v in sorted(counts.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ll")
    ap.add_argument("--json")
    ap.add_argument("--filter", default="")
    a = ap.parse_args()
    lines = open(a.ll, encoding="utf-8", errors="replace").read().splitlines()
    results = []
    i = 0
    while i < len(lines):
        m = FUNC_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fname = m.group(1)
        arg_names, j = parse_signature(m.group(2), lines, i)
        body = []
        k = j + 1
        while k < len(lines) and not lines[k].startswith("}"):
            body.append(lines[k])
            k += 1
        if a.filter in fname:
            results.append(census_function(fname, arg_names, body))
        i = k + 1

    for r in results:
        print(f"\n=== {r['function']} ===")
        print("  args:", ", ".join(x or "?" for x in r["args"]))
        print("  addrspace totals:", r["addrspace_totals"])
        if r["other"]:
            print("  other:", r["other"])
        for buf, c in r["per_buffer"].items():
            widths = {k: v for k, v in c.items() if re.match(r"(load|store)_w", k)}
            print(f"  {buf:28s} loads={c.get('loads',0):4d} "
                  f"load_B={c.get('load_bytes',0):5d} "
                  f"stores={c.get('stores',0):3d} "
                  f"store_B={c.get('store_bytes',0):4d}  {widths}")
    if a.json:
        json.dump(results, open(a.json, "w"), indent=2)
        print(f"\nwrote {a.json}")
    if not results:
        print("no matching function", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
