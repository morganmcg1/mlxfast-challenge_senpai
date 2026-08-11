#!/usr/bin/env python3
"""Sigma-of-one-official-draw probe: find submitted commits whose SCORED tree is
byte-identical, so their official score difference is a direct replicate of the
official instrument's noise.

Identity is decided by git OBJECT IDs only (`git cat-file --batch-check` on
`<sha>:Sources`, `<sha>:Vendor`, `<sha>:benchmark.json` and `<sha>^{tree}`).
No diff content is ever read or printed.

Usage: python3 research/tools/sigma_pseudoreplicate_probe.py <corpus.tsv>
  corpus.tsv columns: submission  status  score  commit  created
"""
import collections
import math
import subprocess
import sys


def batch_check(specs):
    p = subprocess.run(["git", "cat-file", "--batch-check"],
                       input="\n".join(specs), capture_output=True, text=True)
    out = []
    for line in p.stdout.strip().split("\n"):
        parts = line.split()
        ok = len(parts) >= 3 and parts[1] in ("commit", "tree", "blob")
        out.append(parts[0] if ok else "MISSING")
    return out


def main(path):
    rows = []
    for line in open(path):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        rows.append(dict(sub=f[0], status=f[1], score=float(f[2]),
                         commit=f[3], created=f[4]))
    print("corpus rows: %d  distinct commits: %d"
          % (len(rows), len({r['commit'] for r in rows})))

    have = batch_check([r["commit"] for r in rows])
    rows_p = [r for r, h in zip(rows, have) if h != "MISSING"]
    print("commits present in this clone: %d of %d" % (len(rows_p), len(rows)))

    specs = []
    for r in rows_p:
        c = r["commit"]
        specs += [c + ":Sources", c + ":Vendor", c + ":benchmark.json", c + "^{tree}"]
    ids = batch_check(specs)
    for i, r in enumerate(rows_p):
        q = ids[4 * i:4 * i + 4]
        r["scored"] = tuple(q[:3])
        r["full"] = q[3]

    groups = collections.defaultdict(list)
    for r in rows_p:
        groups[r["scored"]].append(r)
    mult = [v for v in groups.values() if len(v) > 1]
    print("distinct scored trees: %d" % len(groups))
    print("scored trees drawn >= 2 times: %d" % len(mult))

    diffs = []
    for v in sorted(mult, key=lambda v: -len(v)):
        print("---- k=%d scored_Sources_tree=%s" % (len(v), v[0]["scored"][0][:10]))
        vs = sorted(v, key=lambda r: r["created"])
        for r in vs:
            print("     %s %-8s %.8f  %-18s full_tree=%s"
                  % (r["sub"], r["status"], r["score"], r["created"], r["full"][:10]))
        base = sum(r["score"] for r in vs) / len(vs)
        for a in range(len(vs)):
            for b in range(a + 1, len(vs)):
                d = vs[b]["score"] - vs[a]["score"]
                diffs.append(d / base * 100.0)
                print("     pair %s/%s  delta=%+.8f  (%+.4f %% of %.6f)"
                      % (vs[a]["sub"], vs[b]["sub"], d, d / base * 100.0, base))

    if diffs:
        m = len(diffs)
        sd = math.sqrt(sum(d * d for d in diffs) / (2.0 * m))
        print("\nPAIRED ESTIMATE  m=%d pairs  sigma_hat = sqrt(mean(d^2)/2) = %.4f %% (relative)"
              % (m, sd))
        print("(pairs inside a k>2 group are not independent; report k=2 groups separately)")
    else:
        print("\nNO identical-scored-tree pairs in this clone: paired sigma is not estimable here.")


if __name__ == "__main__":
    main(sys.argv[1])
