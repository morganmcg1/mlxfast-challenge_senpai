#!/bin/bash
# Research-only helper for PR #441 Stage 2.
#
# 1. Drift guard: the harness carries byte-identical copies of the two shipped
#    MSL generators and the ordinal header. Diff them against the submitted
#    source so a later edit to either kernel cannot silently invalidate the
#    equivalence evidence.
# 2. Build and run the bit-exactness harness.
set -uo pipefail
cd "$(dirname "$0")/.."

SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
HARNESS=research/nezuko_q12_router_tournament_bitwise.swift
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Emit a whole Swift declaration: from the matching line to the first `}` at
# column 0 that is not inside a `"""` literal (the MSL bodies contain their own
# column-0 closing braces).
extract_decl() {
  awk -v pat="$2" '
    !on && $0 ~ pat { on = 1 }
    !on { next }
    { print }
    instr && /^[[:space:]]*"""[[:space:]]*$/ { instr = 0; next }
    !instr && /"""[[:space:]]*$/ { instr = 1; next }
    !instr && /^}$/ { exit }
  ' "$1"
}

extract_header() {
  awk '
    /^private let lagunaDecodeRouterOrdinalHeader = """$/ { on = 1; next }
    on && /^"""$/ { exit }
    on { print }
  ' "$1"
}

drift=0
compare_pair() {
  local label="$1" a="$2" b="$3"
  if [ ! -s "$a" ] || [ ! -s "$b" ]; then
    echo "DRIFT GUARD FAILED: could not extract $label"
    drift=1
    return
  fi
  if diff -u "$a" "$b" > "$TMP/d.txt"; then
    echo "drift guard OK: $label ($(wc -l < "$a" | tr -d ' ') lines identical)"
  else
    echo "DRIFT GUARD FAILED for $label:"
    cat "$TMP/d.txt"
    drift=1
  fi
}

for pat in \
  'private func lagunaDecodeRouterOrdinalKernelSource[(]' \
  'private func lagunaDecodeRouterTournamentOrdinalKernelSource[(]'
do
  extract_decl "$SRC" "$pat" > "$TMP/src.txt"
  extract_decl "$HARNESS" "$pat" > "$TMP/harness.txt"
  compare_pair "$pat" "$TMP/src.txt" "$TMP/harness.txt"
done

extract_header "$SRC" > "$TMP/hdr.src"
extract_header "$HARNESS" > "$TMP/hdr.harness"
compare_pair "lagunaDecodeRouterOrdinalHeader" "$TMP/hdr.src" "$TMP/hdr.harness"

if [ "$drift" -ne 0 ]; then
  echo "RESULT: INVALID -- harness no longer matches the submitted kernels."
  exit 3
fi

swiftc -O "$HARNESS" -o "$TMP/bitwise" -framework Metal -framework Foundation || exit 4
"$TMP/bitwise" "${1:-4096}"
