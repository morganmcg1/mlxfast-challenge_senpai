"""Digest of the exact submitted surface (benchmark.json editablePaths).

Rule 75 wants a content identity per leg. Because research/ is not submitted,
every R106-E draw uploads the same bytes; this digest is the constant that
claim rests on.
"""
import hashlib
import json
import os

entries = sorted(json.load(open("benchmark.json"))["editablePaths"])
files, missing, dirs = [], [], 0
for p in entries:
    if os.path.isfile(p):
        files.append(p)
    elif os.path.isdir(p):
        dirs += 1
        for root, _sub, names in os.walk(p):
            files.extend(os.path.join(root, n) for n in names)
    else:
        missing.append(p)

files = sorted(set(files))
h = hashlib.sha256()
total = 0
biggest = ("", 0)
for p in files:
    b = open(p, "rb").read()
    total += len(b)
    if len(b) > biggest[1]:
        biggest = (p, len(b))
    h.update(p.encode())
    h.update(b"\0")
    h.update(hashlib.sha256(b).digest())

print(f"entries       : {len(entries)}  ({dirs} dirs expanded, {len(missing)} missing)")
for m in missing:
    print("  MISSING:", m)
print(f"files         : {len(files)}")
print(f"total bytes   : {total}  (cap 3000000, headroom {3000000 - total})")
print(f"largest file  : {biggest[0]} = {biggest[1]} B (cap 524288, headroom {524288 - biggest[1]})")
print(f"payload sha256: {h.hexdigest()}")
