"""r128-P: warm-on vs warm-off contrast for the timed 512-token prefill (H-M4B)."""
import csv
import math
import pathlib

ART = pathlib.Path("research/artifacts/r128p")


def load(name):
    with open(ART / name) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def stats(xs):
    n = len(xs)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return n, m, sd


def step_seconds(prefix, n):
    out = []
    for i in range(1, n + 1):
        for line in open(ART / f"{prefix}-{i}.log"):
            if "decode 128/128 tokens" in line:
                out.append(float(line.split("mean_step_seconds=")[1].split()[0]))
                break
    return out


def first_step(prefix, n):
    out = []
    for i in range(1, n + 1):
        for line in open(ART / f"{prefix}-{i}.log"):
            if "decode 1/128 tokens" in line:
                out.append(float(line.split("last_step_seconds=")[1].split()[0]) * 1e3)
                break
    return out


rows = {"warm-on": load("cold-warm.tsv"), "warm-off": load("nowarm.tsv")}
prefix = {"warm-on": "iterate", "warm-off": "nowarm"}
res = {}
for arm, rr in rows.items():
    p = prefix[arm]
    steps = step_seconds(p, len(rr))
    res[arm] = {
        "prefill_ms": [float(r["cold_s_per_tok"]) * 512 * 1e3 for r in rr],
        "seed_ms": [
            (float(r["decode_s_per_tok"]) - s) * 128 * 1e3 for r, s in zip(rr, steps)
        ],
        "step_ms": [s * 1e3 for s in steps],
        "step1_ms": first_step(p, len(rr)),
    }

for key in ("prefill_ms", "seed_ms", "step_ms", "step1_ms"):
    print(f"\n== {key} ==")
    for arm in ("warm-on", "warm-off"):
        n, m, sd = stats(res[arm][key])
        print(f"  {arm:9s} n={n} mean={m:10.3f} sd={sd:8.3f}")
    n1, m1, s1 = stats(res["warm-off"][key])
    n0, m0, s0 = stats(res["warm-on"][key])
    se = math.sqrt(s1 * s1 / n1 + s0 * s0 / n0)
    d = m1 - m0
    print(
        f"  delta (off-on) = {d:.3f} ms   ratio={m1 / m0:.3f}x   "
        f"se={se:.3f}  t={d / se:.1f}  95%CI=[{d - 2.78 * se:.1f}, {d + 2.78 * se:.1f}]"
    )

# Detection floor achieved on the warm-on timed prefill arm.
# Same convention as r128p-analyse.py: t(.975,n-1)+t(.80,n-1) scaled by sd/sqrt(n).
n, m, sd = stats(res["warm-on"]["prefill_ms"])
mde = (2.776 + 0.941) * sd / math.sqrt(n)
print(
    f"\n== achieved floor, warm-on timed prefill, n={n} ==\n"
    f"  sd={sd:.3f} ms  MDE(alpha=.05 two-sided, power=.80)={mde:.3f} ms = {100 * mde / m:.3f} %"
    f"  -> H-M5-equivalent {97.95 * mde / m:.3f} ms"
)
