#!/bin/bash
# S3: reconstruct the MLX-generated Metal translation unit for the scored decode
# router kernel, mechanically, from committed sources only. Research only.
#
#   bash senpai/tools/agx-census-probe/gen_router_metal.sh [OUTDIR]
#
# Emits into OUTDIR (default /tmp/agx_census):
#   preamble.metal  metal::utils() -- the JIT prelude that
#                   backend/metal/custom_kernel.cpp:71 prepends to every custom
#                   kernel source, extracted from mlx-generated/utils.cpp.
#   header.metal    lagunaDecodeRouterOrdinalHeader, extracted from
#                   Sources/MLXFastModel/LagunaRuntimeModel.swift.
#   body.metal      lagunaPrefillRouterTournamentOrdinalKernelSource(normalizing:
#                   false), with the interpolated epilogue substituted.
#   gen.metal       header + generated signature + body, byte-for-byte per
#                   write_signature() in backend/common/metal_kernel.cpp:51-176.
#                   This is what MLX's `verbose: true` prints.
#   full.metal      preamble.metal + gen.metal -- the exact translation unit
#                   Device::build_library_ compiles.
#
# Every dynamic decision write_signature makes is resolved from the committed
# call site (LagunaRuntimeModel.swift:9951-9958 constructor, :9998-10008
# invocation) plus the two lookup tables in metal_kernel.cpp:
#
#   * dtype spelling comes from get_type_string (backend/common/compiled.cpp:47),
#     so float32 -> "float", bfloat16 -> "bfloat16_t", uint32 -> "uint32_t";
#   * address space is `constant` iff arr.size() < max_constant_array_size == 8
#     (metal_kernel.cpp:19,101). logits has size rows*256 and correction_bias
#     size 256, so both are `device`;
#   * `*_shape` / `*_strides` / `*_ndim` parameters are emitted iff the source
#     text contains that substring (metal_kernel.cpp:214-221) -- it does not;
#   * built-in attributes are emitted in the fixed table order of
#     metal_kernel.cpp:222-242 for every table entry whose name occurs in the
#     source text. This script rescans that table from the vendored source
#     rather than hardcoding the answer.
set -u
cd "$(dirname "$0")/../../.."

RT=Sources/MLXFastModel/LagunaRuntimeModel.swift
MK=Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp
UTILS=Vendor/mlx-swift/Source/Cmlx/mlx-generated/utils.cpp
OUT="${1:-/tmp/agx_census}"
mkdir -p "$OUT"

KERNEL_NAME=laguna_prefill_router_tournament_ordinal_active64_v2
# custom_kernel_<name> then one "_<get_type_string>" per input (no "c" suffix
# because both inputs are >= max_constant_array_size) then one per output.
FUNC_NAME="custom_kernel_${KERNEL_NAME}_bfloat16_t_float_uint32_t_float"

awk '/R"preamble\(/{f=1;next} f&&/^\)preamble";$/{exit} f{print}' "$UTILS" > "$OUT/preamble.metal"
awk '/^private let lagunaDecodeRouterOrdinalHeader = """$/{f=1;next} f&&/^"""$/{exit} f{print}' "$RT" > "$OUT/header.metal"
awk '/^private func lagunaPrefillRouterTournamentOrdinalKernelSource/{i=1}
     i&&/^        : """$/{f=1;next} f&&/^"""$/{exit} f{print}' "$RT" > "$OUT/epilogue.metal"
awk '/^private func lagunaPrefillRouterTournamentOrdinalKernelSource/{i=1}
     i&&/^    return """$/{f=1;next} f&&/^"""$/{exit} f{print}' "$RT" > "$OUT/body_raw.metal"

for f in preamble header epilogue body_raw; do
  if [ ! -s "$OUT/$f.metal" ]; then
    echo "extraction failed: $OUT/$f.metal is empty (source layout changed?)" >&2
    exit 1
  fi
done

awk -v epi="$OUT/epilogue.metal" '
  $0 == "\\(epilogue)" { while ((getline l < epi) > 0) print l; close(epi); next }
  { print }
' "$OUT/body_raw.metal" > "$OUT/body.metal"

if grep -q 'epilogue' "$OUT/body.metal"; then
  echo "epilogue interpolation left a marker behind" >&2
  exit 1
fi

BODY="$(cat "$OUT/body.metal")"

# Attribute parameters, in metal_kernel.cpp table order, filtered by substring
# presence in the kernel source -- the same predicate MLX applies.
ATTRS="$(awk '/const std::vector<std::pair<std::string, std::string>> metal_attributes/{f=1;next}
              f&&/^  };$/{exit}
              f&&/\{"/{gsub(/[",{}]/,"");gsub(/^ +| +$/,"");print}' "$MK" \
         | awk -F' *' '{print}' )"

{
  # write_signature appends the user header with no separator, so the header's
  # final "}" and "[[kernel]]" share a line. Reproduce that exactly.
  printf '%s' "$(cat "$OUT/header.metal")"
  printf '[[kernel]] void %s(\n' "$FUNC_NAME"
  printf '  const device bfloat16_t* logits [[buffer(0)]],\n'
  printf '  const device float* correction_bias [[buffer(1)]],\n'
  printf '  device uint32_t* router_indices [[buffer(2)]],\n'
  printf '  device float* router_scores [[buffer(3)]],\n'
  emitted=0
  while IFS= read -r line; do
    attr="${line%% *}"
    dtype="${line##* }"
    [ -z "$attr" ] && continue
    case "$BODY" in *"$attr"*) ;; *) continue ;; esac
    if [ "$emitted" -gt 0 ]; then printf ',\n'; fi
    printf '  %s %s [[%s]]' "$dtype" "$attr" "$attr"
    emitted=$((emitted + 1))
  done <<EOF
$ATTRS
EOF
  printf ') {\n'
  printf '%s' "$BODY"
  printf '\n}\n'
} > "$OUT/gen.metal"

cat "$OUT/preamble.metal" "$OUT/gen.metal" > "$OUT/full.metal"

echo "wrote $OUT/gen.metal ($(wc -c < "$OUT/gen.metal") bytes), $OUT/full.metal ($(wc -c < "$OUT/full.metal") bytes)"
echo "signature:"
sed -n "/^\[\[kernel\]\]/,/) {/p" "$OUT/gen.metal"
