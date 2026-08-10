#!/usr/bin/env python3
"""R105-C: freeze the dispatch-trace evidence into a machine-readable artifact.

Reads every arm dump produced by research/fern_r105c_trace_arm.sh and writes
research/artifacts/fern-r105c/dispatch-summary.json, so the W&B run and the
report cannot drift from the raw traces.

  python3 research/fern_r105c_summarize.py
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib

MARKER = "custom_kernel_laguna_decode_embedding_rope_atlas"


def load(path):
    rows = []
    for line in path.read_text().splitlines():
        p = line.split("\t")
        if len(p) < 5:
            continue
        rows.append((p[1], p[3], p[4]))
    return rows


def marker_index(rows):
    return [i for i, r in enumerate(rows) if MARKER in r[0]]


def summarize(path):
    rows = load(path)
    idx = marker_index(rows)
    out = {
        "bytes": path.stat().st_size,
        "rows": len(rows),
        "md5": hashlib.md5(path.read_bytes()).hexdigest(),
        "markers": len(idx),
        "prefill_rows": idx[0] if idx else len(rows),
        "step_intervals": [b - a for a, b in zip(idx, idx[1:])],
    }
    # steady state = the last complete inter-marker interval
    if len(idx) >= 2:
        lo, hi = idx[-2], idx[-1]
        out["steady_step_dispatches"] = hi - lo
        prof = collections.Counter(rows[lo:hi])
        out["steady_step_profile"] = [
            {"n": n, "kernel": k, "grid": g, "threadgroup": t}
            for (k, g, t), n in sorted(prof.items(), key=lambda kv: (-kv[1], kv[0][0]))
        ]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/tmp/r105c/dump")
    ap.add_argument("--out", default="research/artifacts/fern-r105c/dispatch-summary.json")
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    arms = {}
    for d in sorted(root.iterdir()):
        tsv = d / "dispatch.tsv"
        if tsv.exists():
            arms[d.name] = summarize(tsv)

    base = arms.get("a_base", {})
    for name, a in arms.items():
        a["delta_decode_vs_base"] = (
            a["steady_step_dispatches"] - base["steady_step_dispatches"]
            if "steady_step_dispatches" in a and "steady_step_dispatches" in base else None
        )
        a["delta_prefill_vs_base"] = a["prefill_rows"] - base.get("prefill_rows", a["prefill_rows"])
        a["identical_to_base"] = a["md5"] == base.get("md5")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"arms": arms}, indent=1) + "\n")

    for name, a in arms.items():
        print(f"{name:26s} rows={a['rows']:6d} prefill={a['prefill_rows']:6d} "
              f"step={a.get('steady_step_dispatches')} "
              f"ddec={a['delta_decode_vs_base']} dpre={a['delta_prefill_vs_base']} "
              f"same_as_base={a['identical_to_base']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
