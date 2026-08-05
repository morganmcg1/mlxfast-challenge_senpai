#!/bin/bash
# r5-A: build and run the lane-major/wide bit-for-bit differential harness.
# Must be invoked from the repository root.
set -uo pipefail

PLANES="${PR35_PLANES:-/tmp/pr35_r5a}"
BIN=/tmp/frieren_pr35_bitwise

if [ ! -d "$PLANES" ]; then
  echo "FATAL: plane dump dir $PLANES missing; run research/frieren_pr35_r5a_dump.sh first" >&2
  exit 2
fi

echo "== building harness"
swiftc -O research/frieren_pr35_lanemajor_bitwise.swift \
  -o "$BIN" -framework Metal -framework Foundation || exit 2

echo "== running harness"
"$BIN" --repo . --planes "$PLANES"
