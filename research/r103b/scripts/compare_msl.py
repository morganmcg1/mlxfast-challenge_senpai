#!/usr/bin/env python3
"""R103-B rung 1: compare the JIT MSL corpora captured for two arms."""
import difflib
import hashlib
import pathlib
import sys


def load(arm):
    d = pathlib.Path("/tmp/r103b/dump") / arm
    libs = {}
    for p in sorted(d.glob("lib_*.msl")):
        # lib_0007_<name>.msl -> name comes from library_index.tsv (unsanitized)
        idx = p.name.split("_")[1]
        libs[idx] = p
    names = {}
    ix = d / "library_index.tsv"
    if ix.exists():
        for line in ix.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                names[parts[0]] = parts[1]
    out = {}
    for idx, p in libs.items():
        nm = names.get(idx, p.stem)
        out[nm] = p.read_bytes()
    return out


def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]


def main():
    a_arm, b_arm = sys.argv[1], sys.argv[2]
    a, b = load(a_arm), load(b_arm)
    ka, kb = set(a), set(b)
    only_a = sorted(ka - kb)
    only_b = sorted(kb - ka)
    both = sorted(ka & kb)
    same = [k for k in both if a[k] == b[k]]
    diff = [k for k in both if a[k] != b[k]]

    print(f"# MSL corpus {a_arm} vs {b_arm}")
    print(f"libraries {a_arm}={len(a)} {b_arm}={len(b)}")
    print(f"common={len(both)} byte_identical={len(same)} differing={len(diff)}")
    print(f"only_{a_arm}={len(only_a)} only_{b_arm}={len(only_b)}")
    print()
    if only_a:
        print(f"## only in {a_arm}")
        for k in only_a:
            print(f"  {k}  {len(a[k])}B  {sha(a[k])}")
        print()
    if only_b:
        print(f"## only in {b_arm}")
        for k in only_b:
            print(f"  {k}  {len(b[k])}B  {sha(b[k])}")
        print()
    if diff:
        print("## differing (name, bytes_a, bytes_b, sha_a, sha_b)")
        for k in diff:
            print(f"  {k}  {len(a[k])} -> {len(b[k])}  {sha(a[k])} -> {sha(b[k])}")
        print()
        for k in diff:
            print(f"### unified diff: {k}")
            la = a[k].decode("utf-8", "replace").splitlines()
            lb = b[k].decode("utf-8", "replace").splitlines()
            for line in difflib.unified_diff(
                la, lb, fromfile=f"{a_arm}/{k}", tofile=f"{b_arm}/{k}", lineterm="", n=3
            ):
                print(line)
            print()
    print("## byte-identical library names")
    for k in same:
        print(f"  {k}  {len(a[k])}B  {sha(a[k])}")


if __name__ == "__main__":
    main()
