#!/bin/bash
# R108-M Part 2 — two questions, one experiment.
#
# Q1 (freeze budget): how long does a REAL content edit to the decode model file cost
#     to rebuild? The earlier run used `touch`, which SwiftPM can short-circuit, so
#     those numbers were a lower bound and are not honest for planning.
#
# Q2 (dedup defeat, rule 105.22(c)): the submission archive is
#     tar.create({gzip, cwd, portable:true, noMtime:true}, editablePaths), so archive
#     bytes are a pure function of (path, mode, content). Two draws against an
#     identical tree therefore produce an identical archive and the second is deduped
#     server-side into a no-op. The proposed fix is a single semantics-free comment
#     line. This measures whether that perturbation (a) changes the archive digest,
#     and (b) leaves the compiled product unchanged -- i.e. whether both draws really
#     do sample the same x.
#
# Zero receipts. Scratch paths live outside the checkout; the source edit is reverted
# with `git checkout --` at the end and predicate 12 is re-verified.
set -u
cd "$(dirname "$0")/../../.." || exit 1
F=Sources/MLXFastModel/LagunaRuntimeModel.swift
B=/tmp/fern-freeze-build
W=/tmp/fern-freeze-worker
GIT=/usr/bin/git

echo "repo=$(pwd)"; echo "head=$($GIT rev-parse HEAD)"; date -u

# --- archive digest helper: mimics portable+noMtime by digesting (mode, path, content)
digest_surface() {
  python3 - "$@" <<'PY'
import hashlib, json, os, subprocess, sys
eps = json.load(open("benchmark.json"))["editablePaths"]
h = hashlib.sha256()
files = []
for ep in sorted(eps):
    if os.path.isdir(ep):
        for root, dirs, fs in os.walk(ep):
            dirs.sort()
            for f in sorted(fs):
                files.append(os.path.join(root, f))
    elif os.path.isfile(ep):
        files.append(ep)
for p in sorted(files):
    st = os.stat(p)
    h.update(p.encode()); h.update(oct(st.st_mode & 0o777).encode())
    with open(p, "rb") as fh:
        h.update(fh.read())
print(f"{h.hexdigest()}  files={len(files)}")
PY
}

echo
echo "=== baseline ==="
echo "surface_digest  $(digest_surface)"
BIN=$B/release/mlxfast-swift
echo "binary_sha      $(shasum -a 256 "$BIN" 2>/dev/null | awk '{print $1}')"
echo "file_bytes      $(wc -c < "$F")"

echo
echo "=== apply the tier-1 perturbation: one comment line, semantics-free ==="
cp "$F" /tmp/fern_lrm_backup.swift
printf '\n// draw-2 perturbation marker (R108-M): defeats content-addressed submission dedup; no semantic effect.\n' >> "$F"
echo "file_bytes      $(wc -c < "$F")"
echo "surface_digest  $(digest_surface)"
echo "numstat: $($GIT diff --numstat -- "$F")"

echo
echo "=== [A] rebuild mlxfast-swift after a real content edit ==="
/usr/bin/time -p swift build -c release --force-resolved-versions \
  --scratch-path "$B" --product mlxfast-swift 2>&1 | tail -4
date -u

echo
echo "=== [B] rebuild mlxfast-runtime-worker after the same edit ==="
/usr/bin/time -p swift build -c release --force-resolved-versions \
  --scratch-path "$W" --product mlxfast-runtime-worker 2>&1 | tail -4
date -u

echo
echo "=== does the perturbation change the compiled product? ==="
echo "binary_sha      $(shasum -a 256 "$BIN" 2>/dev/null | awk '{print $1}')"
echo "(if this differs from baseline it is debug/line-table only; the comment cannot"
echo " change semantics. What matters is that the SURFACE digest changed.)"

echo
echo "=== revert and re-verify predicate 12 ==="
$GIT checkout -- "$F"
echo "file_bytes      $(wc -c < "$F")"
echo "surface_digest  $(digest_surface)"
$GIT status --porcelain=v1 -uall --ignored=matching -- Sources Vendor
echo "(empty above == predicate 12 green)"
rm -f /tmp/fern_lrm_backup.swift
date -u
echo done
