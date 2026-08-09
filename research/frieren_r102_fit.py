#!/usr/bin/env python3
"""R102-A rung 1: fit the split-invariant fixed cost of decode attention.

Reads the probe logs written by research/run_frieren_r102_fixed_cost.sh and
emits the gate quantity f/tau0 with a 95% interval, the linearity evidence,
the direct M=0 measurement, and the work-conserving split emulation table.

The ring loop is `i = sg; i + 3*BN < N; i += 4*BN` with BN=32 over 32
simdgroups, so every simdgroup runs exactly M = floor(N/128) iterations for
N in {128m, 128m+32, 128m+64, 128m+96}. M, not N, is the work axis.
"""

import csv
import math
import re
import sys
from pathlib import Path

OUT = Path("research/artifacts/frieren-r102")
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 10: 2.228, 20: 2.086}

E1 = re.compile(r"^\s+(\d+)\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+\S+\s*$")
PAIR = re.compile(
    r"^\s+(\d+)\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([+-][\d.]+)\s+([\d.]+)"
    r"\s+([\d.]+)\s+([+-][\d.]+)\s+([+-][\d.]+)\s*$"
)
REGIME = re.compile(
    r"^\s+(\d+)\s+[\d.]+\s+(\d+)\s+(\d+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+([\d.]+)"
    r"\s+([\d.]+)\s+([\d.]+)\s+(yes|no)\s+(\S+)\s*$"
)


def parse(path):
    """Returns rows, N, and per-K E1/paired/regime records for one probe log."""
    text = path.read_text()
    n = int(re.search(r"attn rows N\s+(\d+)", text).group(1))
    sections = {"regime": {}, "e1": {}, "pair": {}}
    which = None
    for line in text.splitlines():
        if "memory regime" in line:
            which = "regime"
        elif "absolute cost ladder" in line:
            which = "e1"
        elif "paired per-call cost" in line:
            which = "pair"
        if which == "regime" and (m := REGIME.match(line)):
            sections["regime"][int(m.group(1))] = {
                "kvheads": int(m.group(2)), "slots": int(m.group(3)),
                "uniq_MiB": float(m.group(4)), "achieved_GB_s": float(m.group(6)),
                "slc_fit": m.group(8), "regime": m.group(9),
            }
        elif which == "e1" and (m := E1.match(line)):
            sections["e1"][int(m.group(1))] = float(m.group(2))
        elif which == "pair" and (m := PAIR.match(line)):
            sections["pair"][int(m.group(1))] = {
                "base_min": float(m.group(2)), "d_mean": float(m.group(4)),
                "d_sd": float(m.group(5)), "pct": float(m.group(8)),
            }
    return n, sections


def ols(xs, ys):
    """Intercept, slope, R^2 and the intercept/slope covariance for y = a + b x."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in resid)
    sst = sum((y - my) ** 2 for y in ys)
    df = n - 2
    s2 = sse / df
    var_b = s2 / sxx
    var_a = s2 * (1.0 / n + mx * mx / sxx)
    cov_ab = -s2 * mx / sxx
    return {
        "a": a, "b": b, "r2": 1 - sse / sst if sst else float("nan"),
        "var_a": var_a, "var_b": var_b, "cov_ab": cov_ab, "df": df,
        "resid": resid, "rmse": math.sqrt(s2),
    }


def ratio_ci(fit, mmax):
    """f/tau0 with a delta-method 95% interval; tau0 = mmax * slope."""
    a, b = fit["a"], fit["b"]
    tau0 = mmax * b
    r = a / tau0
    d_a = 1.0 / tau0
    d_b = -a / (mmax * b * b)
    var = (d_a ** 2 * fit["var_a"] + d_b ** 2 * fit["var_b"]
           + 2 * d_a * d_b * fit["cov_ab"])
    half = T95[fit["df"]] * math.sqrt(max(var, 0.0))
    return tau0, r, r - half, r + half


def block(tag, ks, label):
    """Fits tau(M) for each K in one block and prints the gate table."""
    pts = {}
    for path in sorted(OUT.glob(f"{tag}_n*.log")):
        n, sec = parse(path)
        pts[n] = sec
    if not pts:
        print(f"  (no logs for {tag})")
        return {}
    print(f"\n### {label}")
    print("\n| K | N | M | t_us (E1 min) | uniq_MiB | slc_fit | regime | "
          "null d_mean_us | null d_sd | null % |")
    print("|--:|--:|--:|--:|--:|:--|:--|--:|--:|--:|")
    for n in sorted(pts, reverse=True):
        for k in ks:
            e1 = pts[n]["e1"].get(k)
            if e1 is None:
                continue
            rg = pts[n]["regime"].get(k, {})
            pr = pts[n]["pair"].get(k, {})
            print(f"| {k} | {n} | {n // 128} | {e1:.3f} | "
                  f"{rg.get('uniq_MiB', float('nan')):.2f} | {rg.get('slc_fit','?')} | "
                  f"{rg.get('regime','?')} | {pr.get('d_mean',float('nan')):+.3f} | "
                  f"{pr.get('d_sd',float('nan')):.3f} | {pr.get('pct',float('nan')):+.3f} |")

    fits = {}
    print("\n| K | f_us (intercept) | c_us/iter | tau0_us | f/tau0 | 95% CI | "
          "R^2 | rmse_us | f_direct(M=0) | verdict |")
    print("|--:|--:|--:|--:|--:|:--|--:|--:|--:|:--|")
    for k in ks:
        xs, ys = [], []
        for n in sorted(pts):
            m = n // 128
            if m >= 1 and k in pts[n]["e1"]:
                xs.append(m)
                ys.append(pts[n]["e1"][k])
        if len(xs) < 3:
            continue
        fit = ols(xs, ys)
        tau0, r, lo, hi = ratio_ci(fit, max(xs))
        direct = pts.get(96, {}).get("e1", {}).get(k)
        v = "GO" if hi < 0.0667 else ("PARTIAL" if r < 0.20 else "NO-GO")
        fits[k] = dict(fit=fit, tau0=tau0, r=r, lo=lo, hi=hi, direct=direct,
                       verdict=v, xs=xs, ys=ys)
        print(f"| {k} | {fit['a']:.3f} | {fit['b']:.3f} | {tau0:.3f} | "
              f"{100*r:.1f}% | [{100*lo:.1f}%, {100*hi:.1f}%] | {fit['r2']:.5f} | "
              f"{fit['rmse']:.3f} | "
              f"{'%.3f' % direct if direct is not None else '-'} | {v} |")
        print(f"|   | residuals M={xs}: "
              f"{['%+.3f' % q for q in fit['resid']]} | | | | | | | | |")
    return fits


def main():
    print("# R102-A rung 1 — split-invariant fixed cost of decode attention\n")
    print("Work axis is M = floor(N/128) ring iterations per simdgroup.")
    print("tau(M) = f + c*M fitted over M in {1,2,3,4}; M=0 (N=96) is an")
    print("independent check, never an input to the fit.")
    print("Gate: GO if f/tau0 and its upper 95% bound < 6.67%; "
          "PARTIAL if < 20%; else NO-GO.")

    res = block("R", [20, 32, 40, 64, 128], "Block R — resident (SLC-served)")
    ded = block("D", [20, 32, 40], "Block D — SLC-defeat, DRAM working set held constant")

    # a (per call) vs phi (per wave): T(40,M) - T(20,M) crosses one wave boundary
    # on a 20-core host, so its intercept is phi and its slope is the extra
    # row-work of the second wave.
    for tag, name in (("R", "resident"), ("D", "defeat")):
        pts = {}
        for path in sorted(OUT.glob(f"{tag}_n*.log")):
            n, sec = parse(path)
            pts[n] = sec
        xs, ys = [], []
        for n in sorted(pts):
            m = n // 128
            e = pts[n]["e1"]
            if m >= 1 and 20 in e and 40 in e:
                xs.append(m)
                ys.append(e[40] - e[20])
        if len(xs) >= 3:
            fit = ols(xs, ys)
            base = pts.get(512, {}).get("e1", {}).get(32)
            print(f"\n### a-vs-phi separation ({name})")
            print("T(K=40) - T(K=20) isolates the second wave: intercept = phi "
                  "(paid once per extra wave), slope = its row work.")
            print(f"\n| quantity | value |\n|:--|--:|")
            print(f"| phi (per-wave fixed cost) | {fit['a']:.3f} us |")
            print(f"| second-wave slope | {fit['b']:.3f} us/iter |")
            print(f"| R^2 | {fit['r2']:.5f} |")
            if base:
                print(f"| T(K=32, N=512) | {base:.3f} us |")

    # M3: work- and byte-conserving split emulation.
    rows = []
    for path in sorted(OUT.glob("M3D_k*.log")):
        k = int(re.search(r"M3D_k(\d+)", path.name).group(1))
        n, sec = parse(path)
        rows.append((k, n, sec["e1"].get(k), sec["regime"].get(k, {}),
                     sec["pair"].get(k, {})))
    if rows:
        rows.sort()
        base = rows[0][2]
        print("\n### Block M3D — direct split emulation under SLC defeat")
        print("Each row does the same total threadgroup-rows and reads the same")
        print("kv-head-rows from the same address spread. Only the threadgroup")
        print("count and rows-per-threadgroup change. This is a LOWER BOUND on a")
        print("real split: it omits the partial (o,m,l) write and the combine pass.")
        print("\n| split S | K | N | M | t_us | uniq_MiB | regime | vs S=1 | "
              "null d_sd |")
        print("|--:|--:|--:|--:|--:|--:|:--|--:|--:|")
        for k, n, t, rg, pr in rows:
            s = k // rows[0][0]
            print(f"| {s} | {k} | {n} | {n // 128} | {t:.3f} | "
                  f"{rg.get('uniq_MiB', float('nan')):.2f} | {rg.get('regime','?')} | "
                  f"{t/base:.4f}x | {pr.get('d_sd', float('nan')):.3f} |")

    with (OUT / "sweep.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["block", "K", "N", "M", "t_us", "uniq_MiB", "slc_fit",
                    "regime", "achieved_GB_s", "null_d_mean_us", "null_d_sd_us",
                    "null_pct"])
        for path in sorted(OUT.glob("*.log")):
            n, sec = parse(path)
            for k, t in sorted(sec["e1"].items()):
                rg = sec["regime"].get(k, {})
                pr = sec["pair"].get(k, {})
                w.writerow([path.stem, k, n, n // 128, f"{t:.4f}",
                            rg.get("uniq_MiB", ""), rg.get("slc_fit", ""),
                            rg.get("regime", ""), rg.get("achieved_GB_s", ""),
                            pr.get("d_mean", ""), pr.get("d_sd", ""),
                            pr.get("pct", "")])
    print(f"\nwrote {OUT/'sweep.csv'}")
    return res, ded


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
