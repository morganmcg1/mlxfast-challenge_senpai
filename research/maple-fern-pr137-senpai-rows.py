import json

rows = json.load(open("feed.json"))
if isinstance(rows, dict):
    rows = rows["submissions"]

out = []
for r in rows:
    note = (r.get("note") or "")
    if note.lstrip().lower().startswith("model: senpai") or "\nModel: senpai" in note:
        m = r.get("officialMetrics") or {}
        out.append((
            r.get("createdAt"), r.get("id", "")[:8], r.get("status"),
            r.get("officialScore"), m.get("decode_seconds_per_token"),
            m.get("decode_speedup"), note.splitlines()[0][:60] if note else "",
        ))

print("senpai-model rows: %d" % len(out))
hdr = "%-24s %-9s %-9s %-18s %-14s %-10s" % (
    "createdAt", "id", "status", "officialScore", "decode s/tok", "dspd")
print(hdr)
for t, i, s, sc, d, ds, n in sorted(out):
    print("%-24s %-9s %-9s %-18s %-14s %-10s" % (
        t, i, s, sc, d, ds))

print()
print("--- all rows between 97a5090c (2026-08-06T05:04) and ours (2026-08-06T23:29) ---")
for r in rows:
    ca = r.get("createdAt") or ""
    if "2026-08-06T05:04" <= ca <= "2026-08-06T23:30":
        m = r.get("officialMetrics") or {}
        note = (r.get("note") or "").lstrip()
        first = note.splitlines()[0][:48] if note else ""
        print("%-24s %-9s %-9s %-18s %-12s %s" % (
            ca, r.get("id", "")[:8], r.get("status"), r.get("officialScore"),
            m.get("decode_seconds_per_token"), first))
