#!/usr/bin/env python3
"""One-off probe: how does the ranked wrapper build officialScore from the receipt?

Fetches the six r105-A receipts, dumps every officialMetrics key once, then for
each receipt compares officialScore against the reported-speedup product and
against pinned / paired reconstructions.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "research" / "r105a-receipts.json"
CAL_DEC = 0.013890
CAL_PRE = 0.0003845


def api(path: str) -> dict:
    cfg = json.loads((pathlib.Path.home() / ".config" / "mlxfast" / "config.json").read_text())
    request = urllib.request.Request(
        cfg["apiBaseUrl"].rstrip("/") + path,
        headers={"Authorization": f"Bearer {cfg['token']}"},
    )
    return json.load(urllib.request.urlopen(request, timeout=120))


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    subs = []
    for entry in manifest:
        sid = entry["submission_id"]
        sub = api(f"/api/submissions/{urllib.parse.quote(sid, safe='')}")["submission"]
        subs.append((entry["arm"], sub))

    print("== submission top-level keys ==")
    print(sorted(subs[0][1].keys()))
    print()
    print("== officialMetrics keys ==")
    print(json.dumps(sorted(subs[0][1]["officialMetrics"].keys()), indent=0))
    print()
    print("== full officialMetrics for A0-1 ==")
    print(json.dumps(subs[0][1]["officialMetrics"], indent=1, sort_keys=True))
    print()

    hdr = ("arm", "official", "rep_prod", "pinned", "paired", "off/rep", "off/pinned", "off/paired")
    print(("{:<6}" + "{:>14}" * 7).format(*hdr))
    for arm, sub in subs:
        m = sub["officialMetrics"]
        off = sub["officialScore"]
        rd, rp = m["decode_speedup"], m["prefill_speedup"]
        rep = rd**0.75 * rp**0.25
        pin = (CAL_DEC / m["decode_seconds_per_token"]) ** 0.75 * (
            CAL_PRE / m["prefill_seconds_per_token"]
        ) ** 0.25
        pair = (m["baseline_decode_seconds_per_token"] / m["decode_seconds_per_token"]) ** 0.75 * (
            m["baseline_prefill_seconds_per_token"] / m["prefill_seconds_per_token"]
        ) ** 0.25
        print(
            ("{:<6}" + "{:>14.7f}" * 3 + "{:>14.7f}" + "{:>14.6f}" * 3).format(
                arm, off, rep, pin, pair, off / rep, off / pin, off / pair
            )
        )

    print()
    print("== reported speedups vs pinned / paired ratios ==")
    for arm, sub in subs:
        m = sub["officialMetrics"]
        rd, rp = m["decode_speedup"], m["prefill_speedup"]
        pin_d = CAL_DEC / m["decode_seconds_per_token"]
        pin_p = CAL_PRE / m["prefill_seconds_per_token"]
        pair_d = m["baseline_decode_seconds_per_token"] / m["decode_seconds_per_token"]
        pair_p = m["baseline_prefill_seconds_per_token"] / m["prefill_seconds_per_token"]
        print(
            f"{arm:<6} dec rep={rd:.7f} pin={pin_d:.7f} pair={pair_d:.7f}   "
            f"pre rep={rp:.7f} pin={pin_p:.7f} pair={pair_p:.7f}"
        )

    print()
    print("== baseline-lottery decomposition (control = A0 mean baseline limbs) ==")
    a0 = [m for arm, s in subs if arm.startswith("A0") for m in (s["officialMetrics"],)]
    mbd = sum(m["baseline_decode_seconds_per_token"] for m in a0) / len(a0)
    mbp = sum(m["baseline_prefill_seconds_per_token"] for m in a0) / len(a0)
    print(f"control mean baseline_dec={mbd!r} baseline_pre={mbp!r}")
    rows = {}
    hdr = ("arm", "official", "hybrid", "lot_dec", "lot_pre", "lottery", "cand_part")
    print(("{:<6}" + "{:>13}" * 2 + "{:>12}" * 4).format(*hdr))

    for arm, sub in subs:
        m = sub["officialMetrics"]
        hyb = (mbd / m["decode_seconds_per_token"]) ** 0.75 * (
            mbp / m["prefill_seconds_per_token"]
        ) ** 0.25
        lot_d = 0.75 * math.log(m["baseline_decode_seconds_per_token"] / mbd)
        lot_p = 0.25 * math.log(m["baseline_prefill_seconds_per_token"] / mbp)
        rows[arm] = (sub["officialScore"], hyb, lot_d, lot_p)
        print(
            ("{:<6}" + "{:>13.7f}" * 2 + "{:>12.6f}" * 4).format(
                arm, sub["officialScore"], hyb, lot_d, lot_p, lot_d + lot_p, math.log(hyb)
            )
        )

    print()
    print("== A1-1 vs A1-2 swing decomposition (natural log of official score) ==")
    o1, h1, d1, p1 = rows["A1-1"]
    o2, h2, d2, p2 = rows["A1-2"]
    print(f"official A1-1={o1:.7f} A1-2={o2:.7f} delta={o1 - o2:+.7f}")
    print(f"dln official     = {math.log(o1 / o2):+.6f}")
    print(f"  lottery part   = {(d1 + p1) - (d2 + p2):+.6f}  (dec {d1 - d2:+.6f}, pre {p1 - p2:+.6f})")
    print(f"  candidate part = {math.log(h1 / h2):+.6f}")
    print(f"A1-1 official minus its own hybrid: {o1 - h1:+.7f}  ({100 * (o1 / h1 - 1):+.3f}%)")
    print(f"A1-2 official minus its own hybrid: {o2 - h2:+.7f}  ({100 * (o2 / h2 - 1):+.3f}%)")

    print()
    print("== verdicts on the fully un-paired score (control-mean baseline limbs) ==")
    t95 = {2: 2.920, 3: 2.353}
    ctrl = [rows[a][1] for a in ("A0-1", "A0-2", "A0-3")]
    m0 = statistics.mean(ctrl)
    s0 = statistics.stdev(ctrl)
    print(f"control n=3 mean={m0:.7f} sigma={s0:.7f} CV={100 * s0 / m0:.4f}%")
    for name, members in (("A1", ("A1-1", "A1-2")), ("A2", ("A2-1",))):
        vals = [rows[a][1] for a in members]
        n = len(vals)
        delta = statistics.mean(vals) - m0
        se = s0 * math.sqrt(1.0 / n + 1.0 / 3.0)
        t = t95[2 + (n - 1)]
        print(
            f"{name} n={n} delta={delta:+.7f} SE={se:.7f} z={delta / se:+.2f} "
            f"CI90=[{delta - t * se:+.7f}, {delta + t * se:+.7f}]"
        )


if __name__ == "__main__":
    main()
