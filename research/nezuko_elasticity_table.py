#!/usr/bin/env python3
"""Turn a sweep_dispatch_elasticity.sh log into the elasticity census table.

    research/nezuko_elasticity_table.py <sweep log> [...]

Each injected arm is compared against a drift-corrected base reference: the
linear interpolation between the nearest preceding and following `base` arm in
run order. Interpolating rather than using a single global base is what keeps a
slow thermal or DVFS trend from being read as a family effect.
"""
import re
import sys

HEAD = re.compile(r"^=+ (\w+) (\S*) SPLIT=(\d+) STEPS=(\d+) =+$")
STEP = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms .* cbs=([\d.]+) "
    r"dispatches=([\d.]+)"
)
BOUND = re.compile(r"GPUINJECT (\w+) bound (\S+)")


def parse(paths):
    arms = []
    cur = None
    for path in paths:
        with open(path) as fh:
            for line in fh:
                m = HEAD.match(line.strip())
                if m:
                    cur = {
                        "mode": m.group(1),
                        "pattern": m.group(2),
                        "split": int(m.group(3)),
                        "steps": int(m.group(4)),
                        "bound": [],
                    }
                    arms.append(cur)
                    continue
                if cur is None:
                    continue
                m = STEP.search(line)
                if m:
                    cur["wall"] = float(m.group(1)) * 1000.0
                    cur["union"] = float(m.group(3)) * 1000.0
                    cur["gap"] = float(m.group(4)) * 1000.0
                    cur["cbs"] = float(m.group(5))
                    cur["nops"] = float(m.group(6))
                    continue
                m = BOUND.search(line)
                if m:
                    cur["bound"].append(m.group(2))
    return [a for a in arms if "wall" in a]


def interp(arms, i, key):
    """Drift-corrected base value at arm index i."""
    lo = max((j for j in range(i) if arms[j]["mode"] == "base"), default=None)
    hi = min(
        (j for j in range(i + 1, len(arms)) if arms[j]["mode"] == "base"),
        default=None,
    )
    if lo is None and hi is None:
        raise SystemExit("no base arm in log")
    if lo is None:
        return arms[hi][key]
    if hi is None:
        return arms[lo][key]
    w = (i - lo) / (hi - lo)
    return arms[lo][key] * (1 - w) + arms[hi][key] * w


def main():
    arms = parse(sys.argv[1:])
    bases = [a for a in arms if a["mode"] == "base"]
    if bases:
        wall = [a["wall"] for a in bases]
        union = [a["union"] for a in bases]
        gap = [a["gap"] for a in bases]
        n = len(bases)
        mean = lambda v: sum(v) / len(v)
        sd = lambda v: (
            (sum((x - mean(v)) ** 2 for x in v) / (len(v) - 1)) ** 0.5
            if len(v) > 1
            else 0.0
        )
        print(f"base arms: n={n}")
        print(
            f"  wall  {mean(wall):8.1f} +/- {sd(wall):5.1f} us/step"
            f"   (spread {max(wall) - min(wall):5.1f})"
        )
        print(
            f"  union {mean(union):8.1f} +/- {sd(union):5.1f} us/step"
            f"   (spread {max(union) - min(union):5.1f})"
        )
        print(
            f"  gap   {mean(gap):8.1f} +/- {sd(gap):5.1f} us/step"
            f"   (spread {max(gap) - min(gap):5.1f})"
        )
        print()

    hdr = (
        "| arm | bound | dn | d(union) us | d(wall) us | d(gap) us "
        "| carry d(wall)/d(union) | d(gap)/dn us |"
    )
    print(hdr)
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for i, a in enumerate(arms):
        if a["mode"] == "base":
            continue
        du = a["union"] - interp(arms, i, "union")
        dw = a["wall"] - interp(arms, i, "wall")
        dg = a["gap"] - interp(arms, i, "gap")
        dn = a["nops"] - interp(arms, i, "nops")
        carry = f"{dw / du:6.2f}" if abs(du) > 1e-9 else "n/a"
        per = f"{dg / dn:6.2f}" if abs(dn) > 1e-9 else "n/a"
        print(
            f"| `{a['mode']}:{a['pattern']}` | {len(a['bound'])} "
            f"| {dn:+.0f} | {du:+8.1f} | {dw:+8.1f} | {dg:+7.1f} "
            f"| {carry} | {per} |"
        )

    pts = []
    for i, a in enumerate(arms):
        if a["mode"] == "base":
            continue
        pts.append(
            (
                a["union"] - interp(arms, i, "union"),
                a["wall"] - interp(arms, i, "wall"),
                a["nops"] - interp(arms, i, "nops"),
                a["gap"] - interp(arms, i, "gap"),
            )
        )
    if len(pts) >= 2:
        print()
        fit(
            "d(wall) = a*d(union) + b",
            [p[0] for p in pts],
            [p[1] for p in pts],
        )
        fit(
            "d(gap)  = a*d(n) + b    ",
            [p[2] for p in pts],
            [p[3] for p in pts],
        )


def fit(label, xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - a * mx
    resid = [y - (a * x + b) for x, y in zip(xs, ys)]
    syy = sum((y - my) ** 2 for y in ys)
    ss = sum(r * r for r in resid)
    r2 = 1 - ss / syy if syy else float("nan")
    rms = (ss / n) ** 0.5
    print(f"{label}: a={a:+.4f} b={b:+8.2f} R^2={r2:.4f} rms={rms:.1f} n={n}")


if __name__ == "__main__":
    main()
