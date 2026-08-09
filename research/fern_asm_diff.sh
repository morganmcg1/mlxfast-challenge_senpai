#!/usr/bin/env bash
# Normalised instruction-level diff of one symbol across two linked images.
#
# Addresses, immediate offsets and symbol operands are erased so that only the
# instruction sequence itself is compared. Trailing linker branch islands parked
# in inter-function padding show up as extra trailing `b` lines.
set -euo pipefail

BASE_BIN="${1:?usage: fern_asm_diff.sh <base bin> <cand bin> <mangled symbol>}"
CAND_BIN="${2:?usage: fern_asm_diff.sh <base bin> <cand bin> <mangled symbol>}"
SYM="${3:?usage: fern_asm_diff.sh <base bin> <cand bin> <mangled symbol>}"

OBJDUMP="$(xcrun --find llvm-objdump)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

for side in base cand; do
  bin="${BASE_BIN}"
  [[ "${side}" == "cand" ]] && bin="${CAND_BIN}"
  "${OBJDUMP}" -d --no-show-raw-insn "--disassemble-symbols=${SYM}" "${bin}" \
    | sed -E 's/^[[:space:]]*[0-9a-f]+:[[:space:]]*//; s/0x[0-9a-f]+/HEX/g; s/<[^>]*>/SYM/g; s/#[0-9]+/#IMM/g' \
    | grep -vE '^$|file format|^HEX SYM:|SYM:$' >"${TMP}/${side}.asm"
done

b=$(wc -l <"${TMP}/base.asm" | tr -d ' ')
c=$(wc -l <"${TMP}/cand.asm" | tr -d ' ')
if diff -q "${TMP}/base.asm" "${TMP}/cand.asm" >/dev/null; then
  echo "IDENTICAL (${b} insns)  ${SYM:0:110}"
else
  echo "DIFFERS  base=${b} cand=${c} insns  ${SYM:0:110}"
  diff "${TMP}/base.asm" "${TMP}/cand.asm" | head -20
fi
