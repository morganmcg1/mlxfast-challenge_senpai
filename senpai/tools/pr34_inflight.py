#!/usr/bin/env python3
"""List non-terminal submissions so a `1 submission in flight` conflict can be attributed.

Fetch the corpus first:
  curl -sS -o /tmp/subs.json -H "Authorization: Bearer ${MLXFAST_API_TOKEN}" \
    "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions"
"""
import json
import sys

TERMINAL = {"rejected", "accepted", "failed", "promoted", "superseded"}


def rows(payload):
    if isinstance(payload, dict):
        for key in ("submissions", "items", "data", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return payload if isinstance(payload, list) else []


def note_title(note):
    """First markdown heading of a submission note, used to attribute a shared-account slot."""
    lines = [ln.strip() for ln in (note or "").splitlines()]
    heads = [ln for ln in lines if ln.startswith("#")]
    return (heads[0] if heads else "(no heading)")[:110]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs.json"
    with open(path) as fh:
        payload = json.load(fh)
    all_rows = rows(payload)
    if "--keys" in sys.argv:
        sample = sorted(all_rows, key=lambda r: str(r.get("createdAt", "")))[-1]
        print("row keys:", sorted(sample.keys()))
        print("\n".join(
            f"  {k} = {str(sample[k])[:120]}"
            for k in sorted(sample.keys())
            if k != "officialMetrics"
        ))
        return
    live = [r for r in all_rows if str(r.get("status", "")).lower() not in TERMINAL]
    live.sort(key=lambda r: str(r.get("createdAt", "")))
    print(f"non-terminal submissions: {len(live)}")
    print("\n".join(
        "  {id} status={st} created={c} solver={usr}\n      {title}".format(
            id=r.get("id", "?"),
            st=r.get("status"),
            c=r.get("createdAt"),
            usr=r.get("solverUsername"),
            title=note_title(r.get("note")),
        )
        for r in live
    ))
    recent = sorted(rows(payload), key=lambda r: str(r.get("createdAt", "")))[-6:]
    print("\nmost recent 6 by createdAt:")
    print("\n".join(
        "  {id} status={st} score={s} created={c} updated={u}".format(
            id=str(r.get("id", "?"))[:8],
            st=r.get("status"),
            s=r.get("officialScore"),
            c=r.get("createdAt"),
            u=r.get("updatedAt"),
        )
        for r in recent
    ))


if __name__ == "__main__":
    main()
