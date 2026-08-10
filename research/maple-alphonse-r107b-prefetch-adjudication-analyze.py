#!/usr/bin/env python3
"""Research-only: adjudicate the round-107-B one-axis contrast from probe logs.

`research/fern_r99_qmv_probe.swift` alternates arm order every round: even
round indices dispatch the reference first, odd indices dispatch the variant
first.  Splitting the printed per-round deltas on that parity gives a direct
read of order sensitivity, which is the failure mode that sank PR #454's
whole-model result (AB +0.33%, BA -0.22%).

Gate (preregistered in the assignment): the kernel-local gain must be at least
0.5%, with a stable sign, or the arm is killed before any model-level timing.
"""

from __future__ import annotations

import pathlib
import re
import statistics
import sys

FAITHFUL_TG = 2048  # 131072 threads / 64 = the shipped routed gate/up dispatch
GATE_PCT = 0.5

ARM_RE = re.compile(r"^--- (\S+)\s+vs reference (\S+) ---$")
ROW_RE = re.compile(
    r"^\s*(\d+)\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([-+][\d.]+)\s+([\d.]+)"
)
DELTA_RE = re.compile(r"^\s*per-round delta TG=(\d+):\s*(.*)$")


def parse(path: pathlib.Path) -> dict[str, dict[int, dict]]:
    arms: dict[str, dict[int, dict]] = {}
    arm = None
    pending: list[int] = []
    for line in path.read_text().splitlines():
        m = ARM_RE.match(line)
        if m:
            arm = m.group(1)
            arms[arm] = {}
            pending = []
            continue
        if arm is None:
            continue
        m = ROW_RE.match(line)
        if m:
            tg = int(m.group(1))
            arms[arm][tg] = {
                "ref_min": float(m.group(2)),
                "var_min": float(m.group(3)),
                "deltas": [],
            }
            pending.append(tg)
            continue
        m = DELTA_RE.match(line)
        if m:
            tg = int(m.group(1))
            if tg in arms[arm]:
                arms[arm][tg]["deltas"] = [float(v) for v in m.group(2).split()]
    return arms


def ci95(xs: list[float]) -> tuple[float, float, float]:
    """mean and the two-sided 95% CI half-width bounds of the mean."""
    n = len(xs)
    mean = statistics.fmean(xs)
    if n < 2:
        return mean, mean, mean
    sem = statistics.stdev(xs) / (n**0.5)
    # normal approximation; n >= 30 by construction in this arm
    half = 1.96 * sem
    return mean, mean - half, mean + half


def report(label: str, path: pathlib.Path) -> dict[str, dict]:
    arms = parse(path)
    print(f"\n### {label}  ({path})")
    out: dict[str, dict] = {}
    for arm, rungs in arms.items():
        print(f"\n  arm {arm}")
        print(
            "    TG    n   ref_us   mean_us       ci95_us          gain%"
            "     ci95%        even%    odd%   n_faster"
        )
        for tg, d in sorted(rungs.items()):
            xs = d["deltas"]
            if not xs:
                continue
            ref = d["ref_min"]
            mean, lo, hi = ci95(xs)
            even = statistics.fmean(xs[0::2])  # reference dispatched first
            odd = statistics.fmean(xs[1::2])  # variant dispatched first
            # gain is stated so that positive means the variant is faster
            g, glo, ghi = (-mean / ref * 100, -hi / ref * 100, -lo / ref * 100)
            print(
                f"  {tg:5d} {len(xs):4d} {ref:8.2f} {mean:+9.3f} "
                f"[{lo:+7.3f},{hi:+7.3f}] {g:+8.3f} [{glo:+7.3f},{ghi:+7.3f}]"
                f" {-even / ref * 100:+7.3f} {-odd / ref * 100:+6.3f}"
                f" {sum(1 for v in xs if v < 0):5d}/{len(xs)}"
            )
            if tg == FAITHFUL_TG:
                out[arm] = {
                    "gain": g,
                    "lo": glo,
                    "hi": ghi,
                    "even": -even / ref * 100,
                    "odd": -odd / ref * 100,
                    "n_faster": sum(1 for v in xs if v < 0),
                    "n": len(xs),
                }
    return out


def main() -> int:
    paths = [pathlib.Path(p) for p in sys.argv[1:]]
    print("=" * 78)
    print("round-107-B: does the shipped depth-1 preload in routed gate/up pay?")
    print("positive gain% = removing the preload is FASTER")
    print(f"faithful rung = TG={FAITHFUL_TG} (production dispatch), gate = {GATE_PCT}%")
    print("=" * 78)

    faithful: dict[str, dict[str, dict]] = {}
    for p in paths:
        mode = "defeat" if "defeat" in p.name else "resident"
        kind = "null" if p.name.startswith("null") else "oneaxis"
        faithful[f"{kind}_{mode}"] = report(f"{kind} / {mode}", p)

    print("\n" + "=" * 78)
    print(f"VERDICT at the faithful TG={FAITHFUL_TG} rung")
    print("=" * 78)
    verdict_pass = False
    for mode in ("resident", "defeat"):
        one = faithful.get(f"oneaxis_{mode}", {})
        null = faithful.get(f"null_{mode}", {})
        cand = next((v for k, v in one.items() if "depth0" in k), None)
        noop = next((v for k, v in one.items() if "noop" in k), None)
        slot = next(iter(null.values()), None)
        if cand is None:
            continue
        print(f"\n  {mode}:")
        print(
            f"    candidate depth0_oneaxis  {cand['gain']:+.3f}% "
            f"[{cand['lo']:+.3f},{cand['hi']:+.3f}]  "
            f"even {cand['even']:+.3f}%  odd {cand['odd']:+.3f}%  "
            f"{cand['n_faster']}/{cand['n']} rounds faster"
        )
        if noop:
            print(
                f"    in-run noop control      {noop['gain']:+.3f}% "
                f"[{noop['lo']:+.3f},{noop['hi']:+.3f}]   (Rule 79 slot null)"
            )
        if slot:
            print(
                f"    same-session null        {slot['gain']:+.3f}% "
                f"[{slot['lo']:+.3f},{slot['hi']:+.3f}]"
            )
        checks = {
            "gain >= 0.5%": cand["gain"] >= GATE_PCT,
            "CI excludes 0": cand["lo"] > 0 or cand["hi"] < 0,
            "sign stable across order": (cand["even"] > 0) == (cand["odd"] > 0),
            "sign stable across rounds": cand["n_faster"] in (0, cand["n"]),
            "noop control inside +-0.5%": noop is None or abs(noop["gain"]) < GATE_PCT,
        }
        for name, ok in checks.items():
            print(f"      [{'PASS' if ok else 'FAIL'}] {name}")
        if mode == "defeat" and all(checks.values()):
            verdict_pass = True

    print(
        "\n  GATE: "
        + (
            "OPEN -- proceed to the cooled full-model ABBA stage."
            if verdict_pass
            else "CLOSED -- kill the arm before any model-level timing."
        )
    )
    print(
        "  (the defeated/cache-cold regime is the decisive one: the scored decode\n"
        "   step streams 1671 MB and cannot be served from the SLC)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
