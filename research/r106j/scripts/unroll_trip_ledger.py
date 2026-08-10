#!/usr/bin/env python3
"""Static trip-count / block-coverage ledger for the sliding-ring unroll.

Kernel constants read from Sources/MLXFastModel/LagunaRuntimeModel.swift
(lagunaPairedSlidingAttention source string, ~line 1516):
    head_dim = 128, window = 512, BN = 32, N = 512
Loop shape for an D-deep unroll:
    int i = sg;
    for (; i + (D-1)*BN < N; i += D*BN) { ...D staged blocks... }
    remainder: for (; i < N; i += BN) { ...1 block... }
"""
N, BN = 512, 32


def ledger(depth):
    per_sg_main, per_sg_rem, union, first = set(), set(), set(), None
    for sg in range(BN):
        blocks = []
        starts = [i for i in range(sg, N, depth * BN) if i + (depth - 1) * BN < N]
        for i in starts:
            blocks += [i + k * BN for k in range(depth)]
        tail = starts[-1] + depth * BN if starts else sg
        rem = [j for j in range(tail, N, BN)]
        blocks += rem
        per_sg_main.add(len(starts))
        per_sg_rem.add(len(rem))
        union.update(blocks)
        if first is None:
            first = sorted(blocks)
        assert len(blocks) == len(set(blocks)), f"duplicate block, depth={depth} sg={sg}"
    return sorted(per_sg_main), sorted(per_sg_rem), len(first), len(union)


for depth in (2, 4, 8):
    main, rem, nblk, nunion = ledger(depth)
    print(f"--- {depth}-deep ---")
    print(f"  main-loop iters/simdgroup : {main}")
    print(f"  remainder iters/simdgroup : {rem}")
    print(f"  blocks per simdgroup      : {nblk}")
    print(f"  union over all {BN} sg      : {nunion} (expect {N})  exact={nunion == N}")
