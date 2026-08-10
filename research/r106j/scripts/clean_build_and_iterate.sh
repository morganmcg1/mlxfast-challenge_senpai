#!/bin/bash
# R106-J: force-clean scored-worker build + one --local-iterate pass.
# Usage: clean_build_and_iterate.sh <label>
# The metallib is preserved across the wipe: its content fingerprint covers
# Vendor/mlx-swift/Source/Cmlx/{mlx,mlx-generated}, which T0/T1 do not touch,
# and benchmark.sh aborts outright when the file is absent.

label="$1"
if [ -z "$label" ]; then
  echo "usage: $0 <label>" >&2
  exit 2
fi

root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$root" || exit 3
art="$root/research/artifacts/maple-fern-r106j"
mkdir -p "$art"

relrel="arm64-apple-macosx/release"
stash="$(mktemp -d)"
if [ -f ".build-worker/$relrel/mlx.metallib" ]; then
  cp ".build-worker/$relrel/mlx.metallib" "$stash/" || exit 4
  cp ".build-worker/$relrel/mlx.metallib.fingerprint" "$stash/" 2>/dev/null
  echo "[stash] metallib preserved: $(shasum -a 256 "$stash/mlx.metallib" | cut -d' ' -f1)"
else
  echo "[stash] no existing metallib; benchmark.sh will regenerate it"
fi

rm -rf .build-worker
mkdir -p ".build-worker/$relrel"
ln -sfn "$relrel" .build-worker/release
if [ -f "$stash/mlx.metallib" ]; then
  cp "$stash/mlx.metallib" ".build-worker/$relrel/" || exit 5
  [ -f "$stash/mlx.metallib.fingerprint" ] && cp "$stash/mlx.metallib.fingerprint" ".build-worker/$relrel/"
fi
rm -rf "$stash"

{
  echo "label=$label"
  echo "head=$(git rev-parse HEAD)"
  echo "dirty=$(git status --porcelain | wc -l | tr -d ' ')"
  echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$art/$label.status"

start=$(date +%s)
./benchmark.sh --local-iterate > "$art/$label.iterate.log" 2>&1
rc=$?
end=$(date +%s)

{
  echo "finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "wall_seconds=$((end - start))"
  echo "rc=$rc"
  for f in ".build-worker/$relrel/mlxfast-runtime-worker" ".build-worker/$relrel/mlx.metallib"; do
    if [ -f "$f" ]; then
      echo "sha256 $(shasum -a 256 "$f" | cut -d' ' -f1) bytes $(stat -f%z "$f") $f"
    else
      echo "missing $f"
    fi
  done
} >> "$art/$label.status"

[ -f score.local-iterate.json ] && cp score.local-iterate.json "$art/$label.score.json"
tail -40 "$art/$label.iterate.log"
exit $rc
