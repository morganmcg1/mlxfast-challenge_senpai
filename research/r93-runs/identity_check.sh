#!/usr/bin/env bash
# Arm A support: is a trailing-comment-only source change machine-code-identical?
# Builds the worker three times: same source twice (determinism control), then
# with only the trailing marker comment rewritten. Prints sha256 of each.
set -uo pipefail
cd "$(dirname "$0")/../.."
F=Sources/MLXFastModel/LagunaRuntimeModel.swift
BIN=.build-worker/release/mlxfast-runtime-worker
ORIG_MARKER="$(tail -1 "$F")"

build() {
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker >/dev/null 2>&1
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null
  if [ $rc -ne 0 ]; then echo "BUILD FAILED rc=$rc"; exit 1; fi
  shasum -a 256 "$BIN" | awk '{print $1}'
}

set_marker() {
  local m="$1"
  perl -0pi -e "s{// senpai-r93-[A-Za-z0-9._-]+\s*\z}{$m\n}" "$F"
}

echo "marker now: $ORIG_MARKER"
A=$(build); echo "build A (as-is)            $A"
touch "$F"
B=$(build); echo "build B (touch, no edit)   $B"
set_marker "// senpai-r93-identity-probe"
C=$(build); echo "build C (comment changed)  $C"
perl -0pi -e "s{// senpai-r93-[A-Za-z0-9._-]+\s*\z}{$ORIG_MARKER\n}" "$F"
D=$(build); echo "build D (marker restored)  $D"

echo
[ "$A" = "$B" ] && echo "determinism (A==B): PASS" || echo "determinism (A==B): FAIL - build is not reproducible"
[ "$A" = "$C" ] && echo "comment-only (A==C): identical binary" || echo "comment-only (A==C): binary differs"
[ "$A" = "$D" ] && echo "restore     (A==D): identical binary" || echo "restore     (A==D): binary differs"
echo
echo "final marker: $(tail -1 "$F")"
git diff --stat -- "$F"
