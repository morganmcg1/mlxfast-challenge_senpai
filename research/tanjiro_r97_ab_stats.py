"""Paired ABBA statistics for the r97 fused-QKV A/B logs."""
import json
import statistics as st
import sys

PREFIX = sys.argv[1] if len(sys.argv) > 1 else "research/r97-logs/ab"
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
ORDER = ["off,on", "on,off"]


def load(path):
    d = json.load(open(path))
    m = d["metrics"]
    return dict(
        pre=m["prefill_seconds_per_token"] * 512000.0,
        dec=m["decode_seconds_per_token"] * 1000.0,
        ok=bool(d["passed"]),
        score=d["score"],
        psu=m.get("prefill_speedup"),
        dsu=m.get("decode_speedup"),
        golden=m.get("golden_digest") or m.get("golden_hash"),
        mad=m.get("max_abs_diff"),
    )


rows = []
for i in range(1, REPS + 1):
    rows.append({t: load(f"{PREFIX}.{i}.{t}.json") for t in ("off", "on")})

print("rep order    pre_off  pre_on    dpre    dec_off dec_on   ddec")
for i, r in enumerate(rows):
    dp = r["on"]["pre"] - r["off"]["pre"]
    dd = r["on"]["dec"] - r["off"]["dec"]
    print(
        f"{i+1}   {ORDER[i % 2]:7s} {r['off']['pre']:8.2f} {r['on']['pre']:8.2f}"
        f" {dp:+8.2f} {r['off']['dec']:7.3f} {r['on']['dec']:7.3f} {dd:+7.3f}"
    )

dps = [r["on"]["pre"] - r["off"]["pre"] for r in rows]
dds = [r["on"]["dec"] - r["off"]["dec"] for r in rows]


def sem(x):
    return st.mean(x), (st.stdev(x) / len(x) ** 0.5 if len(x) > 1 else float("nan"))


mp, sp = sem(dps)
md, sd = sem(dds)
print(f"\nprefill delta mean {mp:+.3f} ms  sem {sp:.3f}  n={len(dps)} paired")
print(f"decode  delta mean {md:+.4f} ms  sem {sd:.4f}")
print(f"prefill 95% CI approx [{mp-2.0*sp:+.3f}, {mp+2.0*sp:+.3f}] ms")

print("\ncorrectness passed (off,on):", [(r["off"]["ok"], r["on"]["ok"]) for r in rows])
print("max_abs_diff:", sorted({r[t]["mad"] for r in rows for t in ("off", "on")}, key=str))
print("golden digests:", sorted({str(r[t]["golden"])[:12] for r in rows for t in ("off", "on")}))
print("pre_off:", [round(r["off"]["pre"], 2) for r in rows])
print("pre_on :", [round(r["on"]["pre"], 2) for r in rows])
print("dec_off:", [round(r["off"]["dec"], 4) for r in rows])
print("dec_on :", [round(r["on"]["dec"], 4) for r in rows])
