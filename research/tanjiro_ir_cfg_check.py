#!/usr/bin/env python3
"""Prove the M2 shadow MMA is not sunk into its runtime-false guard.

The offline instruction census shows the shadow `mma` was emitted. That is not
the same as showing it runs. Its only consumer is a store under
`if (run_skip_pct > 1000)`, which is never true, so a compiler would be within
its rights to sink the whole chain into the guard. If it did, M2 would add a
never-taken branch and nothing else, and a flat M2 receipt would be an
instrument failure rather than evidence about the MMA pipe.

This reads the LLVM IR that the Metal front end already emits and answers two
questions per probe:

1. Which basic block holds each `matmul2d_op_run_cooperative` call, and is that
   block on the unconditional fall-through path rather than dominated by the
   guard compare?
2. Do the memory and barrier op classes move at all between probe 0 and the arm?

Generate the inputs first, one directory per probe:

    for p in 0 1 2 3; do
      PROBE=$p BK=64 EMIT_IR=1 OUT_DIR=/tmp/naxpb$p research/nax_msl_compile_check.sh
    done
    research/tanjiro_ir_cfg_check.py /tmp/naxpb0 /tmp/naxpb1 /tmp/naxpb2 /tmp/naxpb3
"""

import pathlib
import re
import sys

KERNEL = re.compile(r'^define .*?@"?(fp_gather_qmm_rhs_expert_nax_check[^"(]*)"?\(')
LABEL = re.compile(r"^([A-Za-z0-9._$-]+):")
INSTR = re.compile(r"^\s+(%\S+ = |call |tail call |br |store |ret |unreachable)")
GUARD = re.compile(r"icmp \w+ i32 %\d+, 1000\b")

OPS = {
    "dev_load": re.compile(r"load .*addrspace\(1\)\*"),
    "tg_load": re.compile(r"load .*addrspace\(3\)\*"),
    "tg_store": re.compile(r"store .*addrspace\(3\)\*"),
    "barrier": re.compile(r"air\.wg\.barrier"),
    "mma": re.compile(r"matmul2d_op_run_cooperative"),
    "int_alu": re.compile(
        r"=\s+(add|sub|mul|shl|lshr|ashr|and|or|xor|udiv|urem|sdiv|srem"
        r"|zext|sext|trunc|icmp)\b"
    ),
    "flt_alu": re.compile(r"=\s+(fadd|fsub|fmul|fdiv|fpext|fptrunc|fcmp)\b"),
}
AXES = list(OPS)


def kernels(path):
    """Split unit.ll into {kernel name: [(line number, text), ...]}."""
    out = {}
    name = None
    for number, text in enumerate(path.read_text().split("\n"), 1):
        match = KERNEL.match(text)
        if match:
            name = match.group(1)
            out[name] = []
        elif text.startswith("}"):
            name = None
        elif name:
            out[name].append((number, text))
    return out


def analyse(body):
    counts = dict.fromkeys(AXES, 0)
    instrs = 0
    block = "entry"
    mma_blocks = []
    guard_line = None
    guarded_store = None
    for number, text in body:
        label = LABEL.match(text)
        if label:
            block = label.group(1)
        if INSTR.match(text):
            instrs += 1
        for axis, pattern in OPS.items():
            if pattern.search(text):
                counts[axis] += 1
        if OPS["mma"].search(text):
            mma_blocks.append((number, block))
        if GUARD.search(text):
            guard_line = number
        if re.match(r"\s+store bfloat %", text) and "addrspace(1)" in text:
            guarded_store = (number, block)
    return counts, instrs, mma_blocks, guard_line, guarded_store


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    dirs = [pathlib.Path(a) for a in argv[1:]]
    table = {}
    for directory in dirs:
        unit = directory / "unit.ll"
        if not unit.exists():
            print(f"missing {unit}; run nax_msl_compile_check.sh with EMIT_IR=1")
            return 2
        print(f"=== {directory.name} ===")
        for name, body in kernels(unit).items():
            counts, instrs, mma_blocks, guard, store = analyse(body)
            # Drop the _pbN arm suffix so every probe shares one shape bucket
            # and the delta columns compare like with like.
            shape = re.sub(r"_pb\d+$", "", name.split("_check_")[1])
            print(f"  {shape}: {instrs} ir instrs")
            print(f"    mma sites: {mma_blocks}")
            print(f"    run_skip_pct guard compare: line {guard}")
            print(f"    guarded device store: {store}")
            if guard is not None and store is not None:
                sunk = [b for line, b in mma_blocks if b == store[1]]
                verdict = "SUNK INTO GUARD -- ARM VOID" if sunk else "not in guard block"
                print(f"    verdict: {verdict}")
            table.setdefault(shape, {})[directory.name] = counts
        print()

    for shape, per_probe in table.items():
        names = list(per_probe)
        print(f"--- {shape} ---")
        print("  " + "axis".ljust(10) + "".join(n.rjust(9) for n in names) + "   delta")
        base = per_probe[names[0]]
        for axis in AXES:
            row = "".join(str(per_probe[n][axis]).rjust(9) for n in names)
            deltas = " ".join(f"{per_probe[n][axis] - base[axis]:+d}" for n in names[1:])
            print("  " + axis.ljust(10) + row + "   " + deltas)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
