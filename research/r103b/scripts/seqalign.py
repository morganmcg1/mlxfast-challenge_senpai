import sys, difflib, collections
a_arm, b_arm = sys.argv[1], sys.argv[2]


def load(arm):
    rows = []
    with open(f"dump/{arm}/dispatch.tsv") as f:
        f.readline()
        for ln in f:
            p = ln.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            rows.append(p)
    return rows


A, B = load(a_arm), load(b_arm)


def canon(name):
    return name.replace("_rpg8_keys_v1_pf1_", "_rpg8_keys_v1_")


def key(r, geom=True):
    k = canon(r[1])
    if geom:
        k += "|" + r[3] + "|" + r[4]
    return k


for geom in (False, True):
    ka = [key(r, geom) for r in A]
    kb = [key(r, geom) for r in B]
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    print(f"### alignment (geom={geom}) {a_arm} vs {b_arm}: len {len(ka)} vs {len(kb)}, non-equal opcodes = {len(ops)}")
    for tag, i1, i2, j1, j2 in ops:
        print(f"  {tag} a[{i1}:{i2}] b[{j1}:{j2}]")
        for x in ka[i1:i2][:8]:
            print(f"    - {x}")
        for x in kb[j1:j2][:8]:
            print(f"    + {x}")
    print()


def sig(rows):
    d = collections.defaultdict(collections.Counter)
    for r in rows:
        d[canon(r[1])][(r[2], r[3], r[4], r[5] if len(r) > 5 else "")] += 1
    return d


sa, sb = sig(A), sig(B)
diffk = [k for k in set(sa) & set(sb) if sa[k] != sb[k]]
print(f"### kernels whose (kind,grid,group,args) multiset differs: {len(diffk)}")
for k in sorted(diffk):
    ca, cb = sa[k], sb[k]
    print(f"  {k}")
    for v in sorted(set(ca) | set(cb)):
        if ca[v] != cb[v]:
            print(f"     {ca[v]:>5} -> {cb[v]:>5}   {v}")
