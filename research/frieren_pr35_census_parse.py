#!/usr/bin/env python3
"""Turn DARKBLOOM_SCALE_CENSUS stderr into the PR #35 r3 census tables.

  python3 research/frieren_pr35_census_parse.py /tmp/frieren_c_census.err [out.csv]
"""
import csv
import re
import sys

FIELDS = ("n", "min", "max", "distinct", "rows", "row_span_max", "blocks", "blk_span_max")


def parse(path):
    planes, families, glob = [], [], None
    for raw in open(path, errors="replace"):
        if "scale-census" not in raw:
            continue
        text = raw.split("scale-census", 1)[1].strip()
        rec = {}
        for field in FIELDS:
            m = re.search(r"\b%s=(-?\d+)\b" % field, text)
            if m:
                rec[field] = int(m.group(1))
        for key in ("row_le", "blk_le"):
            m = re.search(r"\b%s=\[([^\]]*)\]" % key, text)
            if m and m.group(1):
                rec[key] = {
                    p.split(":")[0]: float(p.split(":")[1]) for p in m.group(1).split(",")
                }
        m = re.search(r"\bcodes=\[([^\]]*)\]", text)
        if m and m.group(1):
            rec["codes"] = [int(c) for c in m.group(1).split(",")]
        m = re.search(r"\bhist=\[([^\]]*)\]", text)
        if m and m.group(1):
            rec["hist"] = {
                int(p.split(":")[0]): int(p.split(":")[1]) for p in m.group(1).split(",")
            }
        if text.startswith("plane "):
            rec["name"] = text.split()[1]
            planes.append(rec)
        elif text.startswith("family "):
            rec["name"] = text.split()[1]
            families.append(rec)
        elif text.startswith("global"):
            rec["name"] = "global"
            glob = rec
    return planes, families, glob


def table(rows, title):
    print("\n### %s\n" % title)
    print("| plane | n | min | max | distinct | rows | row_span_max | "
          "row_le15 | row_le31 | blk_le15 | blk_le31 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        print("| `%s` | %d | %d | %d | %d | %d | %d | %.6f | %.6f | %.6f | %.6f |" % (
            r["name"], r["n"], r["min"], r["max"], r["distinct"], r["rows"],
            r["row_span_max"], r.get("row_le", {}).get("le15", float("nan")),
            r.get("row_le", {}).get("le31", float("nan")),
            r.get("blk_le", {}).get("le15", float("nan")),
            r.get("blk_le", {}).get("le31", float("nan"))))


def write_csv(planes, path):
    cols = ["name", "n", "min", "max", "distinct", "rows", "row_span_max",
            "blocks", "blk_span_max", "row_le15", "row_le31", "blk_le15", "blk_le31"]
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols)
        for r in planes:
            writer.writerow([
                r.get("name", ""), r.get("n", ""), r.get("min", ""), r.get("max", ""),
                r.get("distinct", ""), r.get("rows", ""), r.get("row_span_max", ""),
                r.get("blocks", ""), r.get("blk_span_max", ""),
                r.get("row_le", {}).get("le15", ""), r.get("row_le", {}).get("le31", ""),
                r.get("blk_le", {}).get("le15", ""), r.get("blk_le", {}).get("le31", ""),
            ])


def main():
    planes, families, glob = parse(sys.argv[1])
    if len(sys.argv) > 2:
        write_csv(planes + families + ([glob] if glob else []), sys.argv[2])
    print("planes=%d families=%d" % (len(planes), len(families)))
    table(families + ([glob] if glob else []), "Family and global aggregates")
    for fam in sorted({p["name"].split(".", 1)[1] for p in planes if "." in p["name"]}):
        sel = [p for p in planes if p["name"].split(".", 1)[1] == fam]
        worst = sorted(sel, key=lambda r: r.get("row_le", {}).get("le15", 1.0))[:6]
        wide = [p for p in sel if p["max"] > 63]
        table(worst, "%s: six layers with the lowest row_le15" % fam)
        if wide:
            table(wide, "%s: layers with a code above 63" % fam)
    if glob:
        hist = glob.get("hist", {})
        total = sum(hist.values())
        top = sorted(hist.items(), key=lambda kv: -kv[1])[:12]
        print("\n### Global code mass\n")
        print("| code | count | share |")
        print("| --- | --- | --- |")
        for code, count in top:
            print("| %d | %d | %.6f |" % (code, count, count / total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
