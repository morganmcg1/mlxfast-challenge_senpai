import os
import re

NAMES = ["run2_base_split0", "run8_base_split0", "run4_cand_split0", "run6_cand_split0"]


def parse(p):
    d = {}
    for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), p + ".txt")):
        m = re.match(r"\s+([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+(.*)$", line.rstrip("\n"))
        if not m:
            continue
        key = m.group(5).replace("top8keys_r1_bf16_v2", "R1").replace("top8idx_r1_bf16_v1", "R1")
        key = "|".join(sorted(key.split("|")))
        d[key] = (float(m.group(1)), float(m.group(3)))
    return d


runs = {n: parse(n) for n in NAMES}
first = runs[NAMES[0]]
keys = sorted(set().union(*[set(r) for r in runs.values()]), key=lambda k: -first.get(k, (0, 0))[0])
print(f"{'baseA':>8}{'baseB':>8}{'candA':>8}{'candB':>8}{'dMean':>8}   n  group")
tb = tc = 0.0
for k in keys:
    v = [runs[n].get(k, (0.0, 0.0))[0] for n in NAMES]
    n = first.get(k, (0, 0))[1]
    mb = (v[0] + v[1]) / 2
    mc = (v[2] + v[3]) / 2
    tb += mb
    tc += mc
    parts = k.split("|")
    short = k if len(k) < 55 else f"[{len(parts)}] {parts[0][:26]}..{parts[-1][-22:]}"
    print(f"{v[0]:8.1f}{v[1]:8.1f}{v[2]:8.1f}{v[3]:8.1f}{mc - mb:8.1f} {n:4.0f}  {short}")
print(f"TOTAL base={tb:.1f} cand={tc:.1f} delta={tc - tb:+.1f}")
