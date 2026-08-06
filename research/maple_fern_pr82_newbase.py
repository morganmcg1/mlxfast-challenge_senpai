#!/usr/bin/env python3
"""Pooled, position-balanced analysis of the PR82 new-base (f2fedd58) screen.

Reads the archived score JSONs and reports, per sequence and pooled:
  decode_gain   = mean(base decode s/tok)  / mean(cand decode s/tok)
  prefill_gain  = mean(base prefill s/tok) / mean(cand prefill s/tok)
  paired        = decode_gain**0.75 * prefill_gain**0.25

Every run is asserted to carry the promoted golden hash, exact correctness
and max_abs_diff == 0, so the arms are certified bit-identical before any
timing number is quoted.
"""
import json
import pathlib
import sys

GOLDEN = "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
WEIGHTS = "aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d"

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "research/pr82-scores-newbase")

# (sequence, position, arm, filename)
RUNS = [
    ("seq1", 1, "B", "score.nb1.B1.json"),
    ("seq1", 2, "C", "score.nb1.C1.json"),
    ("seq1", 3, "C", "score.nb1.C2.json"),
    ("seq1", 4, "B", "score.nb1.B2.json"),
    ("seq2", 1, "C", "score.nb2.C1.json"),
    ("seq2", 2, "B", "score.nb2.B1.json"),
    ("seq2", 3, "B", "score.nb2.B2.json"),
    ("seq2", 4, "C", "score.nb2.C2.json"),
]


def load(name):
    path = ROOT / name
    if not path.exists():
        return None
    doc = json.loads(path.read_text())
    m = doc["metrics"]
    assert m["golden_hash"] == GOLDEN, (name, m["golden_hash"])
    assert m["weights_hash"] == WEIGHTS, (name, m["weights_hash"])
    assert m["passed_correctness"] is True, name
    assert m["max_abs_diff"] == 0, (name, m["max_abs_diff"])
    return {
        "harness": m["harness_hash"],
        "decode": m["decode_seconds_per_token"],
        "prefill": m["prefill_seconds_per_token"],
    }


def mean(xs):
    return sum(xs) / len(xs)


def report(label, rows):
    b_dec = [r["decode"] for r in rows if r["arm"] == "B"]
    c_dec = [r["decode"] for r in rows if r["arm"] == "C"]
    b_pre = [r["prefill"] for r in rows if r["arm"] == "B"]
    c_pre = [r["prefill"] for r in rows if r["arm"] == "C"]
    if not b_dec or not c_dec:
        return None
    dg = mean(b_dec) / mean(c_dec)
    pg = mean(b_pre) / mean(c_pre)
    paired = dg ** 0.75 * pg ** 0.25
    print(f"\n== {label} ==  (n_base={len(b_dec)} n_cand={len(c_dec)})")
    print(f"  base   decode mean {mean(b_dec):.12f}")
    print(f"  cand   decode mean {mean(c_dec):.12f}")
    print(f"  decode_gain       {dg:.9f}   ({(dg - 1) * 100:+.3f} %)")
    print(f"  prefill_gain      {pg:.9f}   ({(pg - 1) * 100:+.3f} %)")
    print(f"  paired_estimate   {paired:.9f}")
    return dg, pg, paired


def spread(label, xs):
    if len(xs) < 2:
        return
    print(f"  {label}: min {min(xs):.12f} max {max(xs):.12f} "
          f"spread {(max(xs) / min(xs) - 1) * 100:+.3f} %")


def main():
    loaded = []
    harness = {}
    for seq, pos, arm, name in RUNS:
        rec = load(name)
        if rec is None:
            print(f"  (missing {name})")
            continue
        rec.update(seq=seq, pos=pos, arm=arm, name=name)
        loaded.append(rec)
        harness.setdefault(arm, set()).add(rec["harness"])

    print("harness_hash per arm (arms must be internally consistent "
          "and mutually distinct):")
    for arm, hs in sorted(harness.items()):
        print(f"  {arm}: {sorted(hs)}")
    assert all(len(hs) == 1 for hs in harness.values()), harness
    assert len({next(iter(hs)) for hs in harness.values()}) == len(harness)

    for seq in ("seq1", "seq2"):
        report(seq, [r for r in loaded if r["seq"] == seq])

    report("POOLED (position-balanced)", loaded)

    print("\n== measured A/A spreads (same arm, same session) ==")
    for arm in ("B", "C"):
        spread(f"arm {arm} decode",
               [r["decode"] for r in loaded if r["arm"] == arm])
        spread(f"arm {arm} prefill",
               [r["prefill"] for r in loaded if r["arm"] == arm])
    spread("all runs decode", [r["decode"] for r in loaded])


if __name__ == "__main__":
    main()
