#!/usr/bin/env python3
"""Human-readable summary of the R106-J ABBA report JSON."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r106j-abba/abba_report.json"
d = json.load(open(path))

for which in ("target", "control"):
    if which not in d:
        continue
    x = d[which]
    print("==", which)
    print("  off means", [round(v, 4) for v in x["off_means"]])
    print("  on  means", [round(v, 4) for v in x["on_means"]])
    print("  off %.4f (sd %.4f)   on %.4f (sd %.4f)"
          % (x["off_mean"], x["off_sd_across_processes"],
             x["on_mean"], x["on_sd_across_processes"]))
    print("  delta %+.4f us/call  se %.4f  t %+.3f  df %.2f  ci95 [%+.4f, %+.4f]"
          % (x["delta"], x["se"], x["t"], x["df"], x["ci95"][0], x["ci95"][1]))
    print("  delta %+.3f us/step  ci95 [%+.3f, %+.3f]"
          % (x["delta_us_per_step"], x["ci95_us_per_step"][0],
             x["ci95_us_per_step"][1]))
    print("  score %+.4f %%  ci95 [%+.4f, %+.4f] %%"
          % (x["pct_of_score"], x["pct_of_score_ci95"][0],
             x["pct_of_score_ci95"][1]))

for which in ("target", "control"):
    key = which + "_paired_by_block"
    if key not in d or "mean_delta_us_per_call" not in d[key]:
        continue
    x = d[key]
    print("==", key, "(drift-free contrast; blocks are the replicates)")
    for rep, b in x["blocks"].items():
        print("   %s off %.4f  on %.4f  delta %+.4f"
              % (rep, b["off_mean"], b["on_mean"], b["delta"]))
    print("  mean %+.4f us/call  sd %.4f  se %.4f  t %+.3f  df %d  "
          "ci95 [%+.4f, %+.4f]"
          % (x["mean_delta_us_per_call"], x["sd_across_blocks"], x["se"],
             x["t"], x["df"], x["ci95_us_per_call"][0],
             x["ci95_us_per_call"][1]))
    print("  %+.3f us/step  ci95 [%+.3f, %+.3f]"
          % (x["mean_delta_us_per_step"], x["ci95_us_per_step"][0],
             x["ci95_us_per_step"][1]))
    print("  score %+.4f %%  ci95 [%+.4f, %+.4f] %%"
          % (x["pct_of_score"], x["pct_of_score_ci95"][0],
             x["pct_of_score_ci95"][1]))

if "wall_ms_per_step" in d:
    w = d["wall_ms_per_step"]
    print("== wall ms/step (coarse cross-check only)")
    print("  off", [round(v, 4) for v in w["off"]])
    print("  on ", [round(v, 4) for v in w["on"]])
    ww = w["welch"]
    print("  delta %+.4f ms  se %.4f  t %+.3f  ci95 [%+.4f, %+.4f]"
          % (ww["delta"], ww["se"], ww["t"], ww["ci95"][0], ww["ci95"][1]))

names = set()
for arm in d["processes"].values():
    for row in arm:
        for n in row["target"].get("kernel_names", []):
            names.add(n)
print("== target kernel names seen:")
for n in sorted(names):
    print("   ", n)
