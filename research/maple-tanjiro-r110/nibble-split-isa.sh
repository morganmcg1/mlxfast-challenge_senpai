#!/bin/bash
# Offline ISA comparison of the three DARKBLOOM_NVFP4_NIBBLE_SPLIT nibble-extract
# forms. Wraps each dumped header in a minimal kernel, compiles it with the same
# Metal toolchain MLX JITs with, and diffs AIR + native disassembly.
#
# A byte-identical native diff proves the arms are the same machine code, which
# is a stronger null than any amount of wall-clock statistics.
#
# usage: nibble-split-isa.sh [EVIDENCE_DIR] [OUT_DIR]
set -uo pipefail

EVID="${1:-research/maple-tanjiro-r110/nibble-evidence}"
OUT="${2:-/tmp/r116b-isa}"
mkdir -p "$OUT"

for arm in 0 1 2; do
  src="${OUT}/arm${arm}.metal"
  # strip the ===QMVHEADER_{BEGIN,END}=== sentinel lines
  sed -e '/^===QMVHEADER_/d' "${EVID}/header_split${arm}.metal" > "$src"
  cat >> "$src" <<'KERNELEOF'

kernel void probe(
    const device uint8_t* weight [[buffer(0)]],
    const device float* input    [[buffer(1)]],
    const device float* scales   [[buffer(2)]],
    device float* out            [[buffer(3)]],
    uint gid [[thread_position_in_grid]]
) {
    float acc[16];
    for (uint i = 0; i < 16; ++i) { acc[i] = input[gid * 16u + i]; }
    float s = laguna_nvfp4_scale(uint8_t(scales[gid]));
    out[gid] = laguna_nvfp4_qdot_16(weight + gid * 8u, acc, s);
}
KERNELEOF

  if ! xcrun -sdk macosx metal -std=metal3.1 -O3 -ffast-math \
        -c "$src" -o "${OUT}/arm${arm}.air" 2> "${OUT}/arm${arm}.build.log"; then
    echo "arm${arm}: METAL COMPILE FAILED (see ${OUT}/arm${arm}.build.log)"
    continue
  fi
  xcrun -sdk macosx metallib "${OUT}/arm${arm}.air" -o "${OUT}/arm${arm}.metallib" \
        2>> "${OUT}/arm${arm}.build.log"
  xcrun -sdk macosx metal-objdump --disassemble "${OUT}/arm${arm}.air" \
        > "${OUT}/arm${arm}.air.txt" 2>> "${OUT}/arm${arm}.build.log"
  echo "arm${arm}: air=$(shasum -a 256 < "${OUT}/arm${arm}.air" | cut -c1-16)" \
       "airtext=$(shasum -a 256 < "${OUT}/arm${arm}.air.txt" | cut -c1-16)" \
       "lib=$(shasum -a 256 < "${OUT}/arm${arm}.metallib" 2>/dev/null | cut -c1-16)"
done

echo "--- AIR instruction counts (bitwise ops in probe) ---"
for arm in 0 1 2; do
  [ -f "${OUT}/arm${arm}.air.txt" ] || continue
  printf 'arm%s  and=%-4s or=%-4s shl=%-4s lshr=%-4s total_lines=%s\n' "$arm" \
    "$(grep -c ' = and ' "${OUT}/arm${arm}.air.txt")" \
    "$(grep -c ' = or ' "${OUT}/arm${arm}.air.txt")" \
    "$(grep -c ' = shl ' "${OUT}/arm${arm}.air.txt")" \
    "$(grep -c ' = lshr ' "${OUT}/arm${arm}.air.txt")" \
    "$(wc -l < "${OUT}/arm${arm}.air.txt" | tr -d ' ')"
done

echo "--- pairwise AIR text diffs (differing lines) ---"
for pair in "0 1" "0 2" "1 2"; do
  set -- $pair
  a="${OUT}/arm${1}.air.txt"; b="${OUT}/arm${2}.air.txt"
  if [ -f "$a" ] && [ -f "$b" ]; then
    echo "  ${1}v${2}: $(diff "$a" "$b" | grep -c '^[<>]')"
  fi
done
