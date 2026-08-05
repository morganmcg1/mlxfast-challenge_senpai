"""D1 tg=8 addendum readout: does the M4 instrument see the chain at all?

The tg=160 ladder fitted three supra-knee points per arm, so
tanjiro-pr47-d1-fit.py assumes n in {1600, 2400, 3200}. The tg=8 addendum has a
different design -- one shared n=0 anchor plus n in {3200, 6400} per arm -- so
the slope is a two-point secant and needs no regression.

Discriminator (see senpai/tools/pr47_d1_tg8_addendum.sh):
  H_host   marginal cost is chain-blind CPU command encode
           => chained ~5.55/14.60 ms, unchained ~5.24/14.07 ms, ratio ~1.0
  H_probe  the chain is what costs, as the standalone probe measured
           => chained ~0.88/4.90 ms, unchained ~0.00/0.00 ms, ratio >> 1

Usage: python3 research/tanjiro-pr47-d1-tg8.py [OUTDIR]
"""
import glob
import json
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "research/tanjiro-pr47"


def load(tag):
    p = os.path.join(OUT, f"d1-tg8-{tag}.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    m = d["metrics"]
    S = 512000 * m["prefill_seconds_per_token"]
    T = 1000 * m["decode_seconds_per_token"] - S / 128
    return {
        "tag": tag, "S": S, "T": T, "commit": m.get("commit"),
        "ok": m.get("passed_correctness"), "diff": m.get("max_abs_diff"),
        "ts": m.get("timestamp"),
    }


present = sorted(os.path.basename(p) for p in glob.glob(os.path.join(OUT, "d1-tg8-*.json")))
print(f"tg=8 points on disk ({len(present)}): {', '.join(present)}\n")

anchor = load("r1-n0")
if anchor is None:
    sys.exit("no n=0 anchor; nothing to difference against")

rows = [anchor]
for n in (3200, 6400):
    for c in (1, 0):
        r = load(f"r1-n{n}-c{c}")
        if r:
            r["n"], r["chain"] = n, c
            rows.append(r)

print(f"{'tag':16} {'S (ms)':>10} {'T (ms)':>9} {'corr':>5} {'diff':>5}")
for r in rows:
    print(f"{r['tag']:16} {r['S']:10.4f} {r['T']:9.5f} {str(r['ok']):>5} {str(r['diff']):>5}")
print()

T0 = anchor["T"]
print(f"n=0 anchor T = {T0:.5f} ms\n")

slopes = {}
for c, name in ((1, "chained"), (0, "unchained")):
    a = load(f"r1-n{3200}-c{c}")
    b = load(f"r1-n{6400}-c{c}")
    if not (a and b):
        print(f"{name}: incomplete")
        continue
    dT32, dT64 = a["T"] - T0, b["T"] - T0
    sec = (b["T"] - a["T"]) / 3200 * 1000  # us per dispatch, 3200->6400
    slopes[name] = sec
    print(f"{name:10} dT(3200) = {dT32:8.5f} ms   dT(6400) = {dT64:8.5f} ms"
          f"   secant = {sec:.4f} us/disp")

if len(slopes) == 2:
    ratio = slopes["chained"] / slopes["unchained"] if slopes["unchained"] else float("inf")
    print(f"\nchained/unchained secant ratio = {ratio:.4f}")
    print("  H_host  predicts ~1.0 (instrument cannot see the chain; D5 still needed)")
    print("  H_probe predicts >> 1 (probe's 3.13x at tg=8; instrument sound on M4)")
    print("\nCAVEAT. The banked pre-receipt M4 companion pair showed absorption is")
    print("SOFT, not a hard knee at 1209, so H_probe's 'unchained = exactly 0.00'")
    print("arm is too strong; read the ratio, not the absolute zero.")
    print("M4 wall clock is inadmissible as an M5 magnitude under the transfer law.")
