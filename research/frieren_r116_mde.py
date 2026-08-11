"""Minimum detectable effect for the R116-A confirmation, from screen scatter.

    python3 research/frieren_r116_mde.py

Reports, per arm, the paired between-block SD and the effect the preregistered
`|t| >= 3` rule can resolve at 3 and 18 blocks: in local microseconds, in true
microseconds after the 1.28x `--local-iterate` under-report, and as a fraction
of the campaign score.

Each SD is estimated from 2 degrees of freedom, so every number here is a wide
estimate rather than a guarantee. It exists so a null result can be reported as
a bound instead of as "no effect".
"""
import json
import statistics

rows = json.load(open("research/frieren_r116_screen_steady.json"))
by_block = {}
for r in rows:
    by_block.setdefault(r["block"], {})[r["arm"]] = r["steady_mean_us"]

SCORE_PER_US = 0.000084
UNDER_REPORT = 1.28
for arm in sorted({r["arm"] for r in rows} - {"ctl"}):
    d = [b[arm] - b["ctl"] for b in by_block.values() if arm in b]
    sd = statistics.stdev(d)
    for n in (3, 18):
        sem = sd / n ** 0.5
        mde = 3 * sem
        print(f"{arm:8} n={n:2} sd={sd:6.1f} sem={sem:5.1f} "
              f"mde_t3={mde:6.1f}us true={mde * UNDER_REPORT:6.1f}us "
              f"score={mde * UNDER_REPORT * SCORE_PER_US * 100:5.3f}%")
