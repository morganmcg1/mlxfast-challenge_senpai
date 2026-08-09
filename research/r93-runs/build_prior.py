#!/usr/bin/env python3
"""Build research/r93-runs/prior.json from every landed receipt.

Receipts are stored as research/r93-runs/receipts/<marker>.json, where <marker>
is `null-<n>` or `ladder-K<k>`. The generated table is spliced into the note we
attach to the next official submission so each note carries the full public
record of what the previous ones measured.
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def order(marker: str):
    if marker.startswith("null-"):
        return (0, int(marker.split("-")[1]))
    if marker.startswith("ladder-K"):
        return (1, int(marker.split("K")[1]))
    return (2, 0)


def main() -> None:
    rows = []
    for path in glob.glob(os.path.join(HERE, "receipts", "*.json")):
        marker = os.path.basename(path)[: -len(".json")]
        sub = json.load(open(path))["submission"]
        m = sub.get("officialMetrics") or {}
        rows.append({
            "marker": marker,
            "id": sub["id"][:8],
            "status": sub.get("status"),
            "cand_dec": m.get("decode_seconds_per_token"),
            "cand_pre": m.get("prefill_seconds_per_token"),
            "bl_dec": m.get("baseline_decode_seconds_per_token"),
            "bl_pre": m.get("baseline_prefill_seconds_per_token"),
            "dec_su": m.get("decode_speedup"),
            "pre_su": m.get("prefill_speedup"),
            "passed_correctness": m.get("passed_correctness"),
            "passed_dec_floor": m.get("passed_decode_speedup_floor"),
            "passed_pre_floor": m.get("passed_prefill_speedup_floor"),
            "timestamp": m.get("timestamp"),
        })
    rows.sort(key=lambda r: order(r["marker"]))
    out = os.path.join(HERE, "prior.json")
    json.dump(rows, open(out, "w"), indent=2)
    print("wrote %s with %d row(s)" % (out, len(rows)))
    for r in rows:
        print(r["marker"], r["id"], r["status"], r["cand_dec"], r["cand_pre"], r["bl_dec"])


if __name__ == "__main__":
    main()
