#!/usr/bin/env python3
"""Explain where fern_vendor_relocate_plan.py's kept bytes go.

Buckets every comment block by the reason it was not (fully) relocated so the
gap against the assignment's byte-recovery estimate is attributable rather than
asserted. Prints the HARD_KEEP hits verbatim because those are the blocks a
reviewer must agree with individually.
"""

import sys
from collections import Counter
from pathlib import Path

from frieren_comment_blocks import blocks
from fern_vendor_relocate_plan import (
    FILES, HARD_KEEP, MIN_RELOCATE_BYTES, REPO, SPLIT_OVERRIDE, VENDOR,
    keep_count,
)

buckets = Counter()
hard_hits = []

for name, _ in FILES:
    rel = f"{VENDOR}/{name}"
    bl, _ = blocks(REPO / rel)
    for start, end, body, unsafe in bl:
        nb = sum(len(x) + 1 for x in body)
        text = "\n".join(body)
        ov = SPLIT_OVERRIDE.get((name, start))
        if ov is not None:
            rb = 0
            for s, e, _sym, _ptr in ov:
                rb += sum(len(x) + 1 for x in body[s - start:e - start + 1])
            buckets["RELOCATED"] += rb
            buckets["hand_audited_keep"] += nb - rb
            continue
        if HARD_KEEP.search(text):
            buckets["hard_keep"] += nb
            hard_hits.append((name, start, end, nb, body[0].strip()[:88]))
            continue
        if len(body) == 1:
            buckets["single_line_abstract"] += nb
            continue
        k = keep_count(body)
        rb = sum(len(x) + 1 for x in body[k:])
        kb = nb - rb
        if rb == 0:
            buckets["abstract_is_whole_block"] += nb
        elif rb < MIN_RELOCATE_BYTES:
            buckets["remainder_below_floor"] += nb
        else:
            buckets["abstract_of_split_block"] += kb
            buckets["RELOCATED"] += rb

total = sum(v for k, v in buckets.items())
print(f"{'bucket':28s} {'bytes':>8s} {'share':>7s}")
for k, v in buckets.most_common():
    print(f"{k:28s} {v:8d} {100.0 * v / total:6.1f}%")
print(f"{'TOTAL POOL':28s} {total:8d}")

print(f"\n--- HARD_KEEP blocks ({len(hard_hits)}) ---")
for name, s, e, nb, first in hard_hits:
    print(f"{name:34s} :{s}-{e:<6d} {nb:6d}B  {first}")
