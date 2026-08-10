"""Decompose named official receipts into executable quality vs baseline draw.

Reads the cached public submissions listing through fern_r109f_receipt_axes and
prints, for each requested receipt id prefix, the published score, the
crown-reference normalized score (executable quality), and the same-session
baseline draw multiplier, plus each quantity's rank in the scored population.

    python3 research/fern_r109f_crown_decompose.py [id-prefix ...]
"""

import importlib.util
import pathlib
import sys

DEFAULT_IDS = ("cc6ddc12", "49c33eb2", "e27f1ce4", "fefaed88", "2054d45b")


def load_axes():
    here = pathlib.Path(__file__).with_name("fern_r109f_receipt_axes.py")
    spec = importlib.util.spec_from_file_location("fern_receipt_axes", here)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(ids):
    ra = load_axes()
    rs = ra.scored(ra.rows())
    by = {r["id"][:8]: r for r in rs}
    draws = sorted((r["officialScore"] / r["_norm"] for r in rs), reverse=True)
    norms = sorted((r["_norm"] for r in rs), reverse=True)
    pubs = sorted((r["officialScore"] for r in rs), reverse=True)
    n = len(rs)
    print(f"scored population n={n}")
    for key in ids:
        r = by.get(key)
        if r is None:
            print(f"{key}: not present in the scored population")
            continue
        m = r["_m"]
        draw = r["officialScore"] / r["_norm"]
        print(
            f"\n{key} {r.get('solverUsername')} {r.get('createdAt')} "
            f"status={r['status']} promotion={r.get('promotionStatus')}"
        )
        print(
            f"  published   {r['officialScore']:.11f}  rank {pubs.index(r['officialScore']) + 1}/{n}"
        )
        print(
            f"  normalized  {r['_norm']:.8f}  rank {norms.index(r['_norm']) + 1}/{n}"
            "   (executable quality, fixed reference)"
        )
        print(
            f"  draw mult   {draw:.6f}       rank {draws.index(draw) + 1}/{n}"
            "   (same-session baseline lottery)"
        )
        print(
            f"  candidate   decode={m['decode_seconds_per_token']:.12f} "
            f"prefill={m['prefill_seconds_per_token']:.12f}"
        )
        print(
            f"  baseline    decode={m['baseline_decode_seconds_per_token']:.12f} "
            f"prefill={m['baseline_prefill_seconds_per_token']:.12f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or list(DEFAULT_IDS)))
