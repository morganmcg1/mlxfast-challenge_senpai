#!/usr/bin/env bash
# Gate G1 for r103-C: prove the comment relocation changes no emitted code.
#
# The oracle is the Swift compiler itself.  Each variant of
# Sources/MLXFastModel/LagunaRuntimeModel.swift is installed in turn, every
# object of the MLXFastModel module is deleted, and the scored worker build
# from benchmark.sh:2022 is re-run from scratch.  The resulting
# LagunaRuntimeModel.swift.o is hashed.
#
# Builds are interleaved ORIG, CAND, ORIG, CAND so one run yields three
# independent facts: A/A determinism, B/B determinism, and A/B identity.  An
# incremental build can replay a cached object and cached diagnostics, so the
# per-variant object wipe is what makes each hash a genuine compilation.
#
#     nezuko_r103c_object_identity.sh ORIG_SWIFT CAND_SWIFT
#
# Exit 0 only when all four hashes agree.
set -uo pipefail

ORIG=${1:?usage: $0 ORIG_SWIFT CAND_SWIFT}
CAND=${2:?usage: $0 ORIG_SWIFT CAND_SWIFT}
TARGET=Sources/MLXFastModel/LagunaRuntimeModel.swift
OBJDIR=.build-worker/arm64-apple-macosx/release/MLXFastModel.build
OBJ="$OBJDIR/LagunaRuntimeModel.swift.o"

test -f "$ORIG" || { echo "missing $ORIG" >&2; exit 2; }
test -f "$CAND" || { echo "missing $CAND" >&2; exit 2; }

RESTORE=$(mktemp /tmp/lrm_restore.XXXXXX.swift)
cp "$TARGET" "$RESTORE"
trap 'cp "$RESTORE" "$TARGET"; rm -f "$RESTORE"' EXIT

build_hash() {
  cp "$1" "$TARGET"
  rm -f "$OBJDIR"/*.o
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    >/tmp/nezuko_g1_build.log 2>&1 ||
    { echo "BUILD FAILED for $1" >&2; tail -20 /tmp/nezuko_g1_build.log >&2; exit 3; }
  # A replayed object would predate the source we just installed.
  [ "$OBJ" -nt "$TARGET" ] || { echo "stale object for $1" >&2; exit 4; }
  shasum -a 256 "$OBJ" | cut -d' ' -f1
}

echo "== G1 interleaved object-identity proof =="
echo "orig: $ORIG ($(wc -c <"$ORIG" | tr -d ' ') bytes)"
echo "cand: $CAND ($(wc -c <"$CAND" | tr -d ' ') bytes)"

A1=$(build_hash "$ORIG"); echo "A1 orig: $A1"
B1=$(build_hash "$CAND"); echo "B1 cand: $B1"
A2=$(build_hash "$ORIG"); echo "A2 orig: $A2"
B2=$(build_hash "$CAND"); echo "B2 cand: $B2"

echo "-- verdicts --"
[ "$A1" = "$A2" ] && echo "A/A determinism: PASS" || { echo "A/A determinism: FAIL"; exit 1; }
[ "$B1" = "$B2" ] && echo "B/B determinism: PASS" || { echo "B/B determinism: FAIL"; exit 1; }
[ "$A1" = "$B1" ] && echo "A/B identity:    PASS" || { echo "A/B identity:    FAIL"; exit 1; }
echo "G1 PASS: emitted object byte-identical across the relocation"
