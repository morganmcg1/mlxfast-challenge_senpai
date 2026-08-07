#!/usr/bin/env python3
"""Per-function op census over metal -S -emit-llvm output.

Usage: a2_census.py A.ll B.ll [FILTER_SUBSTRING]

Counts, per defined function, the resource axes the A2 probe claims not to
touch (MMA, barriers, device traffic, threadgroup traffic) plus the one it
does touch (scalar integer ALU).
"""
import re
import sys
from collections import Counter

FUNC_RE = re.compile(r"^define\s+.*?@([\w$.]+)\(")
INT_ALU = {
    "add", "sub", "mul", "and", "or", "xor", "shl", "lshr", "ashr",
    "udiv", "sdiv", "urem", "srem",
}
FLOAT_ALU = {"fadd", "fsub", "fmul", "fdiv", "frem", "fneg"}


def classify(line):
    """Yield zero or more axis names for one IR line."""
    s = line.strip()
    out = []
    if "@__tensorops_impl_matmul2d_op_run_cooperative" in s:
        out.append("mma")
    if "air.wg.barrier" in s or "air.simdgroup.barrier" in s:
        out.append("barrier")
    if re.match(r"%\S+\s*=\s*(tail\s+)?load\b", s) or s.startswith("load "):
        if "addrspace(1)" in s:
            out.append("dev_load")
        elif "addrspace(3)" in s:
            out.append("tg_load")
        elif "addrspace(2)" in s:
            out.append("const_load")
        else:
            out.append("other_load")
    if re.match(r"(tail\s+)?store\b", s):
        if "addrspace(1)" in s:
            out.append("dev_store")
        elif "addrspace(3)" in s:
            out.append("tg_store")
        else:
            out.append("other_store")
    m = re.match(r"%\S+\s*=\s*([a-z]+)\b", s)
    if m:
        op = m.group(1)
        if op in INT_ALU:
            out.append("int_alu")
        elif op in FLOAT_ALU:
            out.append("float_alu")
        elif op == "call" or op == "tail":
            pass
    # `select`, `icmp`, `zext` etc. deliberately excluded: not issue-bearing
    # ALU work in the sense the arm is measuring.
    return out


AXES = [
    "mma", "barrier", "dev_load", "dev_store", "tg_load", "tg_store",
    "const_load", "other_load", "other_store", "int_alu", "float_alu",
    "instrs",
]


def census(path):
    funcs = {}
    cur = None
    with open(path) as fh:
        for line in fh:
            m = FUNC_RE.match(line)
            if m:
                cur = m.group(1)
                funcs.setdefault(cur, Counter())
                continue
            if line.startswith("}"):
                cur = None
                continue
            if cur is None:
                continue
            c = funcs[cur]
            s = line.strip()
            if s and not s.startswith(";") and not s.endswith(":"):
                c["instrs"] += 1
            for axis in classify(line):
                c[axis] += 1
    return funcs


def norm(name):
    """Collapse the A2 gate out of a mangled name so the shipped and probed
    spellings of load_unsafe_wide line up in the comparison table."""
    n = re.sub(r"16load_unsafe_wideILb(\d)ELb(\d)ELb\dEEEvjPDv4_j",
               r"16load_unsafe_wideILb\1ELb\2EEEvv", name)
    n = re.sub(r"_pb\d+$", "", n)
    return n


def main():
    a, b = sys.argv[1], sys.argv[2]
    filt = sys.argv[3] if len(sys.argv) > 3 else ""
    ca = {norm(k): v for k, v in census(a).items()}
    cb = {norm(k): v for k, v in census(b).items()}
    keys = sorted(set(ca) | set(cb))
    if filt:
        keys = [k for k in keys if filt in k]
    hdr = f"{'function':<62}" + "".join(f"{x:>11}" for x in AXES)
    print(hdr)
    print("-" * len(hdr))
    tot_a, tot_b = Counter(), Counter()
    changed = []
    for k in keys:
        va, vb = ca.get(k, Counter()), cb.get(k, Counter())
        tot_a.update(va)
        tot_b.update(vb)
        if va == vb:
            continue
        changed.append(k)
        short = k if len(k) <= 60 else k[:28] + "..." + k[-29:]
        print(f"{short:<62}" + "".join(
            f"{va.get(x,0):>5}->{vb.get(x,0):<5}" if va.get(x, 0) != vb.get(x, 0)
            else f"{va.get(x,0):>11}" for x in AXES))
    print("-" * len(hdr))
    print(f"{'TOTAL':<62}" + "".join(
        f"{tot_a.get(x,0):>5}->{tot_b.get(x,0):<5}"
        if tot_a.get(x, 0) != tot_b.get(x, 0) else f"{tot_a.get(x,0):>11}"
        for x in AXES))
    print(f"\nfunctions defined: A={len(ca)} B={len(cb)}  "
          f"functions with a changed census: {len(changed)}")
    moved = [x for x in AXES if x != "instrs" and tot_a.get(x, 0) != tot_b.get(x, 0)]
    print("axes that moved:", ", ".join(moved) if moved else "(none)")


if __name__ == "__main__":
    main()
