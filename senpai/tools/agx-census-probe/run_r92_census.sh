#!/usr/bin/env bash
# r92-b stage 2 driver (research only; not part of the submission).
#
# Censuses every custom kernel that the scored decode path actually dispatches,
# on applegpu_g16s and applegpu_g17s, from byte-identical source compiled with
# byte-identical flags. Only -arch varies, so each row pair is a matched null by
# construction.
#
# Compile flags reproduce MLX's runtime options exactly: device.cpp:631 sets
# setFastMathEnabled(false) and device.cpp:632 selects LanguageVersion4_0 on
# macOS 26, which census.sh mirrors as -fno-fast-math -std=metal4.0.
#
# Also runs two controls in the same session:
#   floor.metal    -- re-derives the per-arch __compute floor so the delta can be
#                     floor-corrected from an in-session measurement.
#   encoding.metal -- the rule-42 encoding table (float add / float FMA null,
#                     uint MAD positive) as a live positive+negative control.
#
# Usage: bash senpai/tools/agx-census-probe/run_r92_census.sh KERNEL_DIR OUT_TSV
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KDIR="${1:?usage: run_r92_census.sh KERNEL_DIR OUT_TSV}"
OUT="${2:?usage: run_r92_census.sh KERNEL_DIR OUT_TSV}"

printf 'study\tarch\tfn\tcompute_bytes\n' >"$OUT"

emit() { # study file
  local study="$1" file="$2"
  echo "== $study  $(basename "$file")" >&2
  bash "$HERE/census.sh" "$file" 2>/dev/null |
    awk -v s="$study" 'NR>1 && NF>=3 {print s"\t"$1"\t"$2"\t"$3}' >>"$OUT"
}

emit r92_floor "$HERE/floor.metal"
emit r92_encoding "$HERE/encoding.metal"

for f in "$KDIR"/*.metal; do
  case "$f" in *.gen.metal) continue ;; esac
  emit r92_decode "$f"
done

echo "rows=$(($(wc -l <"$OUT") - 1))" >&2
