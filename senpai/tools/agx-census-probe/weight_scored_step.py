#!/usr/bin/env python3
"""Weight the two-arch census by the exact scored steady-decode dispatch count.

Weights are measured, not assumed: ORDER_TXT is the ordered kernel-name
sequence MLX emitted on the scored local-iterate path, split on
laguna_decode_embedding_rope_atlas (exactly one per decode step). The last two
complete steps are byte-identical multisets, so their shared histogram is the
steady step.

Rule 42: bytes are never converted to instruction counts, and the g16s-minus-g17s
floor delta is a bracket (-16 B plain, 0 B once simdgroup attributes are
declared), so every weighted total is reported as a bracket over that
correction.

Usage: weight_scored_step.py CENSUS_TSV ORDER_TXT
"""
import collections
import re
import sys

census_path, order_path = sys.argv[1], sys.argv[2]

MANGLED = re.compile(r"^custom_kernel_(.+?)(_(?:bfloat16_t|float|uint32_t|uint8_t|int32_t)\w*)$")

bytes_of: dict[str, dict[str, int]] = collections.defaultdict(dict)
with open(census_path) as fh:
    next(fh)
    for line in fh:
        study, arch, fn, nb = line.rstrip("\n").split("\t")
        if study != "r92_decode":
            continue
        m = MANGLED.match(fn)
        bytes_of[m.group(1) if m else fn][arch] = int(nb)

names = [ln.strip() for ln in open(order_path) if ln.strip()]
bounds = [i for i, n in enumerate(names) if n == "laguna_decode_embedding_rope_atlas_bf16_2048_v2"]
steps = [names[a:b] for a, b in zip(bounds, bounds[1:])]
hists = [collections.Counter(s) for s in steps]
steady = None
for i in range(len(hists) - 1, 0, -1):
    if hists[i] == hists[i - 1]:
        steady = hists[i]
        break
if steady is None:
    sys.exit("no two consecutive identical decode steps: cannot claim steady state")

print(f"decode_steps_sampled={len(steps)} steady_dispatches={sum(steady.values())}")
print(f"{'kernel':56s}{'n':>4s}{'g16s':>7s}{'g17s':>7s}{'raw':>6s}{'w_raw':>8s}{'w_hi':>8s}")
pos = net = pos_hi = net_hi = 0
rows = []
for name, n in steady.items():
    per_arch = bytes_of.get(name)
    if not per_arch or len(per_arch) != 2:
        sys.exit(f"kernel dispatched but not censused: {name}")
    g16, g17 = per_arch["applegpu_g16s"], per_arch["applegpu_g17s"]
    d = g17 - g16
    rows.append((n * d, name, n, g16, g17, d))
rows.sort(reverse=True)
for w, name, n, g16, g17, d in rows:
    w_hi = n * (d + 16)
    print(f"{name:56s}{n:4d}{g16:7d}{g17:7d}{d:6d}{w:8d}{w_hi:8d}")
    net += w
    net_hi += w_hi
    if d > 16:
        pos += w
        pos_hi += w_hi
print(f"weighted_positive_excess_bytes_per_step={pos} .. {pos_hi}")
print(f"weighted_net_delta_bytes_per_step={net} .. {net_hi}")
