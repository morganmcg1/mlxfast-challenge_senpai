#!/usr/bin/env python3
"""r103-D rung 0: cryptographic provenance for official submission commits.

Every official receipt carries `submissionCommitSha`, a commit in the ORGANIZER
repository (Layr-Labs/mlxfast-challenge) authored by yukon-autoresearch[bot]
with message "Validate submission <submission-id>".  That commit's tree is the
tree the ranked M5 actually built.  Git blob hashes are content hashes, so
comparing blob SHAs over the editable surface is an exact byte-identity test
between an official run and any local fork commit -- no trust required.

Read-only: unauthenticated GitHub API + local `git ls-tree`.

usage: fern_r103d_provenance.py <official-sha> [<official-sha> ...] -- <local-rev> [...]
"""

import json
import pathlib
import subprocess
import sys
import urllib.request

ORG = "Layr-Labs/mlxfast-challenge"
CACHE = pathlib.Path("/tmp/r103d-trees")
CACHE.mkdir(exist_ok=True)


def api(path):
    key = path.replace("/", "_").replace("?", "_")
    cached = CACHE / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "r103d"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    cached.write_text(json.dumps(data))
    return data


def official_blobs(sha):
    c = api(f"/repos/{ORG}/git/commits/{sha}")
    t = api(f"/repos/{ORG}/git/trees/{c['tree']['sha']}?recursive=1")
    if t.get("truncated"):
        sys.exit(f"tree for {sha} truncated -- need paginated walk")
    blobs = {e["path"]: e["sha"] for e in t["tree"] if e["type"] == "blob"}
    return c, blobs


def local_blobs(rev):
    out = subprocess.run(
        ["git", "ls-tree", "-r", rev], capture_output=True, text=True, check=True
    ).stdout
    blobs = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        _mode, typ, sha = meta.split()
        if typ == "blob":
            blobs[path] = sha
    return blobs


def editable_surface(blobs, editable):
    """Expand benchmark.json editablePaths (files or directory prefixes)."""
    keep = {}
    for p, s in blobs.items():
        for e in editable:
            if p == e or p.startswith(e.rstrip("/") + "/"):
                keep[p] = s
                break
    return keep


def compare(name_a, a, name_b, b):
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    diff = sorted(p for p in set(a) & set(b) if a[p] != b[p])
    same = len(set(a) & set(b)) - len(diff)
    print(f"\n=== {name_a}  vs  {name_b}")
    print(f"  files: {len(a)} vs {len(b)} | identical {same} | differing {len(diff)} "
          f"| only-A {len(only_a)} | only-B {len(only_b)}")
    for p in diff:
        print(f"    DIFF  {p}")
    for p in only_a:
        print(f"    A-ONLY {p}")
    for p in only_b:
        print(f"    B-ONLY {p}")
    return len(diff) + len(only_a) + len(only_b)


def main():
    argv = sys.argv[1:]
    split = argv.index("--")
    off_shas, local_revs = argv[:split], argv[split + 1:]

    editable = json.loads(pathlib.Path("benchmark.json").read_text())["editablePaths"]
    print(f"editablePaths entries: {len(editable)}")

    off = {}
    for sha in off_shas:
        c, blobs = official_blobs(sha)
        surf = editable_surface(blobs, editable)
        off[sha] = surf
        print(f"\nofficial {sha[:8]}  msg={c['message'].splitlines()[0]!r}")
        print(f"  author={c['author']['name']} date={c['author']['date']} "
              f"tree={c['tree']['sha'][:12]} parents={[p['sha'][:8] for p in c['parents']]}")
        print(f"  editable files in tree: {len(surf)} (of {len(blobs)} total blobs)")

    loc = {}
    for rev in local_revs:
        blobs = local_blobs(rev)
        loc[rev] = editable_surface(blobs, editable)
        print(f"local {rev}: editable files {len(loc[rev])}")

    keys = [(f"OFF:{s[:8]}", off[s]) for s in off_shas] + [
        (f"LOC:{r[:12]}", loc[r]) for r in local_revs
    ]
    print("\n\n########## pairwise identity matrix (0 = byte-identical surface)")
    hdr = " " * 18 + "".join(f"{n[:16]:>18s}" for n, _ in keys)
    print(hdr)
    for na, a in keys:
        row = f"{na[:16]:18s}"
        for nb, b in keys:
            d = len(set(a) ^ set(b)) + sum(
                1 for p in set(a) & set(b) if a[p] != b[p]
            )
            row += f"{d:18d}"
        print(row)

    print("\n\n########## detailed diffs")
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            compare(keys[i][0], keys[i][1], keys[j][0], keys[j][1])


if __name__ == "__main__":
    main()
