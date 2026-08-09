#!/bin/bash
# S4-a: census the scored decode router kernel and the Lever 2 census arms in
# the same translation unit and with the same compile flags. Research only.
#
#   bash senpai/tools/agx-census-probe/run_s4a.sh [OUTDIR]
#
# Step 1 reconstructs the real MLX-generated translation unit (gen_router_metal.sh).
# Step 2 builds arms.metal = metal::utils() + lagunaDecodeRouterOrdinalHeader +
#        router_arms.metal, so every probe arm sees the exact prelude, the exact
#        helper definitions and the exact generated signature of the real kernel.
# Step 3 censuses full.metal twice (byte-stability evidence for the S3 gate) and
#        arms.metal once, on every target architecture.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../../.."
OUT="${1:-/tmp/agx_census}"

bash "$HERE/gen_router_metal.sh" "$OUT" || exit 1

cat "$OUT/preamble.metal" "$OUT/header.metal" "$HERE/router_arms.metal" > "$OUT/arms.metal"

echo "== real scored decode router (full.metal), pass 1 =="
bash "$HERE/census.sh" "$OUT/full.metal" || exit 1
echo "== real scored decode router (full.metal), pass 2 (stability) =="
bash "$HERE/census.sh" "$OUT/full.metal" || exit 1
echo "== S4-a census arms (arms.metal) =="
bash "$HERE/census.sh" "$OUT/arms.metal" || exit 1
