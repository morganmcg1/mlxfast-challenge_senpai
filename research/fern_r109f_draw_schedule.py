"""Test whether the official same-session baseline draw has exploitable structure.

The published score factors exactly into executable quality times a
same-session baseline draw multiplier.  If that multiplier were i.i.d. there is
nothing to time; if it clusters by hour, weekday, or queue depth then shot
timing is a free lever.  This prints the draw distribution sliced by UTC hour
and weekday, the autocorrelation between consecutive receipts, and the exact
population percentile of the draw we would need to take the crown.

    python3 research/fern_r109f_draw_schedule.py [required-published-target]
"""

import collections
import importlib.util
import pathlib
import statistics
import sys

CROWN_PUBLISHED = 2.61650354381456


def load_axes():
    here = pathlib.Path(__file__).with_name("fern_r109f_receipt_axes.py")
    spec = importlib.util.spec_from_file_location("fern_receipt_axes", here)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slice_report(title, buckets):
    print(f"\n{title}")
    print(f"  {'bucket':>8} {'n':>5} {'mean':>10} {'sd':>10} {'max':>10} {'p>1.014':>9}")
    for key in sorted(buckets):
        vals = buckets[key]
        if len(vals) < 2:
            continue
        hi = sum(1 for v in vals if v > 1.014) / len(vals)
        print(f"  {key:>8} {len(vals):5d} {statistics.mean(vals):10.6f} "
              f"{statistics.stdev(vals):10.6f} {max(vals):10.6f} {100 * hi:8.1f}%")


def main(target):
    ra = load_axes()
    rs = ra.scored(ra.rows())
    rs.sort(key=lambda r: r.get("createdAt") or "")
    draws = [r["officialScore"] / r["_norm"] for r in rs]
    n = len(rs)
    print(f"scored population n={n}  draw mean={statistics.mean(draws):.6f} "
          f"sd={statistics.stdev(draws):.6f}")

    # exact percentile of the draw we would need, from our recent normalized mean
    mine = [r for r in rs if r.get("solverUsername") == "morganmcg1"][-8:]
    for label, norm in (("recent mean", statistics.mean(r["_norm"] for r in mine)),
                        ("best single", max(r["_norm"] for r in mine))):
        need = target / norm
        hits = sum(1 for d in draws if d > need)
        print(f"  required draw from {label} normalized {norm:.8f}: {need:.6f} "
              f"-> {hits}/{n} historical draws would have won ({100 * hits / n:.3f}%)")

    slice_report("draw multiplier by UTC hour", _bucket(rs, draws, lambda t: f"{t[11:13]}"))
    slice_report("draw multiplier by UTC date", _bucket(rs, draws, lambda t: t[5:10]))

    # lag-1 autocorrelation over receipts ordered by creation time
    a, b = draws[:-1], draws[1:]
    print(f"\nlag-1 autocorrelation of consecutive receipt draws: "
          f"{ra.pearson(a, b):+.4f}  (0 => memoryless lottery, no timing lever)")

    # do the two baseline axes move together within a session?
    bd = [r["_m"]["baseline_decode_seconds_per_token"] for r in rs]
    bp = [r["_m"]["baseline_prefill_seconds_per_token"] for r in rs]
    print(f"corr(baseline_decode, baseline_prefill) = {ra.pearson(bd, bp):+.4f}")

    # regime test: the daily slice suggests the lottery narrowed after 08-08.
    early = [d for r, d in zip(rs, draws) if "2026-08-02" <= (r.get("createdAt") or "")[:10] <= "2026-08-08"]
    late = [d for r, d in zip(rs, draws) if (r.get("createdAt") or "")[:10] >= "2026-08-09"]
    me, ml = statistics.mean(early), statistics.mean(late)
    se, sl = statistics.stdev(early), statistics.stdev(late)
    tstat = (me - ml) / ((se ** 2 / len(early) + sl ** 2 / len(late)) ** 0.5)
    print(f"\nregime test  08-02..08-08 n={len(early)} mean={me:.6f} sd={se:.6f} max={max(early):.6f}")
    print(f"             08-09..now   n={len(late)} mean={ml:.6f} sd={sl:.6f} max={max(late):.6f}")
    print(f"             Welch t={tstat:+.2f}  (a lower draw means a faster, less "
          "beatable same-session baseline)")
    for label, norm in (("recent mean", statistics.mean(r["_norm"] for r in mine)),
                        ("best single", max(r["_norm"] for r in mine))):
        print(f"  ceiling under the late regime from {label} normalized {norm:.8f}: "
              f"{norm * max(late):.8f} vs crown {target:.8f} -> "
              f"{'CLEARS' if norm * max(late) > target else 'SHORT by ' + format(100 * (target / (norm * max(late)) - 1), '.3f') + '%'}")
    need_norm = target / max(late)
    print(f"  normalized score needed to reach the crown at the late-regime best draw "
          f"{max(late):.6f}: {need_norm:.8f}")

    top = sorted(zip(draws, rs), key=lambda x: -x[0])[:12]
    print("\ntop 12 baseline draws ever observed")
    for d, r in top:
        print(f"  {d:.6f} {r['id'][:8]} {r.get('createdAt')} {r.get('solverUsername')} "
              f"pub={r['officialScore']:.8f} norm={r['_norm']:.8f}")
    return 0


def _bucket(rs, draws, keyfn):
    out = collections.defaultdict(list)
    for r, d in zip(rs, draws):
        created = r.get("createdAt") or ""
        if len(created) >= 13:
            out[keyfn(created)].append(d)
    return out


if __name__ == "__main__":
    sys.exit(main(float(sys.argv[1]) if len(sys.argv) > 1 else CROWN_PUBLISHED))
