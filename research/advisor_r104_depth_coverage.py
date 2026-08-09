#!/usr/bin/env python3
"""Verify that every candidate DARKBLOOM_SLIDING_PIPE_DEPTH covers exactly the
same 16 key slots per simdgroup, in the same order -> bit-exact by construction.

Sliding kernel geometry (LagunaRuntimeModel.swift:1508-1526, k-loop 1638-1817):
    N = 512, BN = 32, sg in [0, 32)
    depth d:  int i = sg; for (; i + (d-1)*BN < N; i += d*BN) { a, b, ... }
    each iteration consumes slots i, i+BN, ..., i+(d-1)*BN in that order.
"""


def slots(sg, depth, N=512, BN=32):
    out = []
    i = sg
    while i + (depth - 1) * BN < N:
        for j in range(depth):
            out.append(i + j * BN)
        i += depth * BN
    return out


ok = True
for depth in (1, 2, 4, 8):
    iters = None
    for sg in range(32):
        s = slots(sg, depth)
        ref = slots(sg, 2)  # depth 2 == the OLD/shipped-before-#565 form
        if s != ref:
            ok = False
            print(f"  MISMATCH depth={depth} sg={sg}: {s} != {ref}")
        if sg == 0:
            iters = len(s) // depth
    n = len(slots(0, depth))
    print(f"depth={depth}: {iters:2d} iterations x {depth} slots = {n} slots/simdgroup"
          f"   order-identical to depth 2: {s == ref}")

print()
print("all depths cover identical slot sequences:", ok)
print()
# Coverage completeness: 32 simdgroups x 16 slots = 512 = N, each exactly once.
cov = sorted(x for sg in range(32) for x in slots(sg, 4))
print("union over 32 simdgroups covers 0..511 exactly once:",
      cov == list(range(512)))
print()
print("=> accumulation order per simdgroup is invariant across depth,")
print("   so the depth dial is BIT-EXACT by construction. No tail loop is")
print("   needed at any depth because 16 %% d == 0 for d in {1,2,4,8}.")
