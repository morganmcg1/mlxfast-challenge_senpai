#!/usr/bin/env python3
"""Report the largest idle gaps in a GPUPROF trace, to pick a segmentation
threshold for pr91_census.py."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from prefill_probe import parse_gpuprof  # noqa: E402

recs = sorted(parse_gpuprof(pathlib.Path(sys.argv[1]).read_text(
    errors="replace")))
gaps, prev = [], None
for i, r in enumerate(recs):
    if prev is not None and r[0] > prev:
        gaps.append(((r[0] - prev) * 1e3, i))
    prev = max(prev or r[1], r[1])
gaps.sort(reverse=True)
print(f"records {len(recs)}  dispatches {sum(r[2] for r in recs)}")
print("largest gaps (ms, record index that starts the next block):")
for g, i in gaps[:25]:
    print(f"  {g:10.3f}  @{i}")
