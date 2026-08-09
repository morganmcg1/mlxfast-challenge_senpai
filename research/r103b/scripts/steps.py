import sys, collections

arms = sys.argv[1:]
MARK = "custom_kernel_laguna_decode_embedding_rope_atlas"


def load(arm):
    rows, bad = [], 0
    with open(f"dump/{arm}/dispatch.tsv") as f:
        f.readline()
        for ln in f:
            p = ln.rstrip("\n").split("\t")
            if len(p) < 5 or not p[0].isdigit():
                bad += 1
                continue
            rows.append(p)
    return rows, bad


data = {}
for arm in arms:
    rows, bad = load(arm)
    idx = [i for i, r in enumerate(rows) if r[1].startswith(MARK)]
    segs = []
    for a, b in zip(idx, idx[1:] + [len(rows)]):
        segs.append(rows[a:b])
    prefill = rows[: idx[0]] if idx else rows
    data[arm] = (rows, bad, prefill, segs)
    print(f"[{arm}] rows={len(rows)} malformed_skipped={bad} prefill_dispatches={len(prefill)} "
          f"decode_steps={len(segs)} per_step={[len(s) for s in segs]}")

if len(arms) == 2:
    a, b = arms
    ra, _, pa, sa = data[a]
    rb, _, pb, sb = data[b]
    print(f"\nprefill delta = {len(pb)-len(pa)}")
    for i, (x, y) in enumerate(zip(sa, sb)):
        print(f"decode step {i}: {a}={len(x)} {b}={len(y)} delta={len(y)-len(x)}")
    # tail rows unique to a
    print(f"\ntail rows in {a} beyond aligned prefix:")
    for r in ra[len(rb):]:
        print("   ", r[0], r[1][:90])
