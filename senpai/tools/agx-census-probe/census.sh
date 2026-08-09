#!/bin/bash
# AGX native-instruction census driver (research only; not part of the submission).
#
#   bash senpai/tools/agx-census-probe/census.sh FILE.metal [-- extra metal flags]
#
# For every entry point in FILE.metal, compiles a metallib, runs the AGX native
# translator (`applegpu-nt`) for each target architecture, and reports the
# __compute section size of the resulting native binary.
#
# Output is TSV: arch  fn  compute_bytes  delta_vs_floor  instr_est
#
# WARNING about instr_est: it is (compute_bytes - floor) / 8.0. AGX uses
# variable-length instruction encodings, so 8 B/instruction is only an average
# for one particular opcode mix. `encoding.metal` measures 11.2-11.8 B/iter for
# an immediate-operand FMA ladder. Treat `compute_bytes` as the observable and
# only compare instr_est between arms with a similar opcode mix.
#
# WARNING about the floor: the empty-kernel floor depends on the kernel
# signature and on which arguments the compiler keeps alive. A kernel whose
# buffer loads get dead-stripped can land *below* the nominal floor. Always
# pair an arm with a matched null that has the identical signature.
set -u

FILE="${1:-}"
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "usage: census.sh FILE.metal [-- extra metal flags]" >&2
  exit 2
fi
shift
if [ "${1:-}" = "--" ]; then shift; fi
EXTRA=("$@")

STD="${MTL_STD:--std=metal4.0}"
FASTMATH="${MTL_FASTMATH:--fno-fast-math}"
ARCHS="${AGX_ARCHS:-applegpu_g16s applegpu_g17s}"
PLATFORM_ARGS=(-platform_version macos 26.0 26.5)

WORK="$(mktemp -d /tmp/agx_census.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

AIR="$WORK/x.air"
LIB="$WORK/x.metallib"

xcrun metal "$STD" "$FASTMATH" "${EXTRA[@]+${EXTRA[@]}}" -c "$FILE" -o "$AIR" || exit 1
xcrun metallib "$AIR" -o "$LIB" || exit 1

# Entry-point discovery from the metallib symbol table. Grepping the .metal text
# fails for macro-generated kernels, so use the compiled FUNCTION_LIST instead.
FNS="$(xcrun metal-objdump --syms "$LIB" | awk '/FUNCTION_LIST/ {print $NF}')"
if [ -z "$FNS" ]; then
  echo "no entry points found in $FILE" >&2
  exit 1
fi

printf 'arch\tfn\tcompute_bytes\n'
for arch in $ARCHS; do
  for fn in $FNS; do
    json="$WORK/s_$fn.mtlp-json"
    printf '{ "pipelines": { "compute_pipelines": [ { "compute_function": "%s" } ] } }\n' "$fn" > "$json"
    bin="$WORK/${arch}_${fn}.bin"
    if ! xcrun applegpu-nt -arch "$arch" "${PLATFORM_ARGS[@]}" -N "$json" "$LIB" -o "$bin" >"$WORK/nt.log" 2>&1; then
      printf '%s\t%s\tNT_FAIL\n' "$arch" "$fn"
      sed -n '1,4p' "$WORK/nt.log" >&2
      continue
    fi
    # metal-size prints "\tSection __compute: 1792" -> the size is $NF, not $2.
    bytes="$(xcrun metal-size -m "$bin" | awk '/Section __compute:/ {print $NF; exit}')"
    printf '%s\t%s\t%s\n' "$arch" "$fn" "${bytes:-NA}"
  done
done
