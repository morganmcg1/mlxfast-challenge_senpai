#!/usr/bin/env bash
# Offline MSL compile check for the regular-NAX steel GEMM JIT source
# (`steel_gemm_fused_nax`), used by PR #293 (H2 skinny-N tile downsize).
#
# M4 hosts report Apple GPU generation 16 and never select the `_nax` kernels,
# so no local benchmark run ever JIT-compiles this source. This script
# reproduces get_steel_gemm_fused_nax_kernel()'s concatenation order from
# Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp:979-1010
#     metal::utils() + metal::gemm_nax() + metal::steel_gemm_fused_nax()
#     + get_template_definition(lib_name, "gemm", type, bm, bn, bk, wm, wn,
#                               transpose_a, transpose_b)
# and hands the result to the offline Metal compiler. That is the only local way
# to prove a proposed (bm, bn, bk, wm, wn) geometry is dispatchable before
# spending an official M5 submission.
#
# Note the JIT emits EIGHT template args (AccumType defaults to float); the AOT
# macro in steel_gemm_fused_nax.metal:15 passes `float` explicitly as a ninth.
# We mirror the JIT form because jit_kernels.cpp is the compiled path
# (Vendor/mlx-swift/Package.swift:25 sources it, :284 excludes nojit_kernels).
# `transpose_*` are streamed as bools through an ostringstream, so they appear
# as 0/1, not true/false.
#
# Usage: research/tanjiro_steel_nax_compile_check.sh [BM BN BK WM WN]
#   BM..WN         tile geometry (default 64 128 256 2 4 = the M5 incumbent)
#   TYPE=<t>       element type string (default bfloat16_t)
#   TRANS=<nn|nt|tn|tt>  transpose pair (default nt, i.e. y = x @ W^T)
#   GEN_DIR=<dir>  override the mlx-generated directory
#   OUT_DIR=<dir>  override the scratch output directory
#   EMIT_LIB=1     also link a .metallib
#   STATS=1        with EMIT_LIB=1, create the pipeline on the local device and
#                  report maxTotalThreadsPerThreadgroup / threadgroup memory.
#                  Expected to FAIL on a gen-16 host: the AIR is valid but the
#                  local GPU cannot realise NAX MMA instructions.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="${GEN_DIR:-${REPO_ROOT}/Vendor/mlx-swift/Source/Cmlx/mlx-generated}"
BM="${1:-64}"; BN="${2:-128}"; BK="${3:-256}"; WM="${4:-2}"; WN="${5:-4}"
TYPE="${TYPE:-bfloat16_t}"
TRANS="${TRANS:-nt}"
OUT="${OUT_DIR:-/tmp/steel_nax_check_${BM}x${BN}x${BK}_w${WM}x${WN}_${TRANS}}"
mkdir -p "${OUT}"

case "${TRANS}" in
  nn) TA=0; TB=0 ;;
  nt) TA=0; TB=1 ;;
  tn) TA=1; TB=0 ;;
  tt) TA=1; TB=1 ;;
  *) echo "bad TRANS=${TRANS}" >&2; exit 2 ;;
esac

# Legality per steel_gemm_fused_nax.h:150-155: SM=BM/WM, SN=BN/WN, TM=SM/16,
# TN=SN/16 must all be positive integers, so BM/WM and BN/WN must each be a
# positive multiple of 16.
SM=$(( BM / WM )); SN=$(( BN / WN ))
if (( BM % WM != 0 || BN % WN != 0 || SM % 16 != 0 || SN % 16 != 0 || SM == 0 || SN == 0 )); then
  echo "ILLEGAL GEOMETRY bm${BM} bn${BN} wm${WM} wn${WN}: SM=${SM} SN=${SN} (need multiples of 16)"
  exit 3
fi
echo "geometry bm${BM} bn${BN} bk${BK} wm${WM} wn${WN} ${TRANS}: SM=${SM} SN=${SN} SK=32 TM=$((SM/16)) TN=$((SN/16)) threads/TG=$((WM*WN*32)) simdgroups=$((WM*WN))"

extract() {
  awk '
    /R"preamble\(/ { inb = 1; next }
    /^\)preamble";?$/ { inb = 0; next }
    inb { print }
  ' "$1"
}

NAME="steel_gemm_fused_nax_${TRANS}_bfloat16_bfloat16_bm${BM}_bn${BN}_bk${BK}_wm${WM}_wn${WN}"
SRC="${OUT}/unit.metal"
: > "${SRC}"
{
  echo "// ---- metal::utils() ----"
  extract "${GEN}/utils.cpp"
  echo "// ---- metal::gemm_nax() ----"
  extract "${GEN}/gemm_nax.cpp"
  echo "// ---- metal::steel_gemm_fused_nax() ----"
  extract "${GEN}/steel_gemm_fused_nax.cpp"
  echo "// ---- get_template_definition(kernels.h:404-424) ----"
  targs="${TYPE}, ${BM}, ${BN}, ${BK}, ${WM}, ${WN}, ${TA}, ${TB}"
  cat <<EOF
template [[host_name("${NAME}")]] [[kernel]] decltype(gemm<${targs}>) gemm<${targs}>;
EOF
} >> "${SRC}"

echo "generated $(wc -l < "${SRC}") lines -> ${SRC}"

status=1
for std in metal4.0 metal3.2 ""; do
  args=(-x metal -Wall -Wextra -fno-fast-math -Wno-c++17-extensions -Wno-c++20-extensions)
  [ -n "${std}" ] && args+=("-std=${std}")
  log="${OUT}/compile${std:+.${std}}.log"
  if xcrun -sdk macosx metal "${args[@]}" -c "${SRC}" -o "${OUT}/unit.air" > "${log}" 2>&1; then
    echo "COMPILE OK (std=${std:-default}) -> ${OUT}/unit.air"
    status=0
    break
  fi
  echo "compile failed (std=${std:-default}); first errors:"
  grep -E "error:" "${log}" | head -15
done

if [ "${status}" -eq 0 ] && [ "${EMIT_LIB:-0}" = "1" ]; then
  if xcrun -sdk macosx metallib "${OUT}/unit.air" -o "${OUT}/unit.metallib" \
      > "${OUT}/metallib.log" 2>&1; then
    echo "METALLIB OK -> ${OUT}/unit.metallib ($(wc -c < "${OUT}/unit.metallib") bytes)"
  else
    echo "metallib link failed:"; head -15 "${OUT}/metallib.log"; status=1
  fi
fi

if [ "${status}" -eq 0 ] && [ "${EMIT_LIB:-0}" = "1" ] && [ "${STATS:-0}" = "1" ]; then
  cat > "${OUT}/stats.swift" <<'EOF'
import Metal
// The kernel is specialised by function constants 10/100/110/200/201/202
// (steel_gemm_fused_nax.h:5-12), so it must be fetched with constantValues.
// Values below are matmul.cpp's for the wk/wv class: no batch, no out source,
// no axpby, and all three alignment predicates true.
let libPath = CommandLine.arguments[1]
let fnName = CommandLine.arguments[2]
guard let dev = MTLCreateSystemDefaultDevice() else { print("STATS: no device"); exit(1) }
print("STATS device=\(dev.name)")
let cv = MTLFunctionConstantValues()
for (value, index) in [(false, 10), (false, 100), (false, 110),
                       (true, 200), (true, 201), (true, 202)] {
  var v = value
  cv.setConstantValue(&v, type: .bool, index: index)
}
do {
  let lib = try dev.makeLibrary(URL: URL(fileURLWithPath: libPath))
  let fn = try lib.makeFunction(name: fnName, constantValues: cv)
  let pso = try dev.makeComputePipelineState(function: fn)
  print("STATS ok name=\(fnName)")
  print("STATS maxTotalThreadsPerThreadgroup=\(pso.maxTotalThreadsPerThreadgroup)")
  print("STATS staticThreadgroupMemoryLength=\(pso.staticThreadgroupMemoryLength)")
  print("STATS threadExecutionWidth=\(pso.threadExecutionWidth)")
} catch {
  print("STATS pipeline/library creation failed: \(error)")
  exit(1)
}
EOF
  if xcrun swiftc -O "${OUT}/stats.swift" -o "${OUT}/stats" > "${OUT}/statsbuild.log" 2>&1; then
    "${OUT}/stats" "${OUT}/unit.metallib" "${NAME}" || \
      echo "STATS unavailable on this host (expected on Apple GPU gen 16; AIR is still valid)"
  else
    echo "stats host build failed:"; head -15 "${OUT}/statsbuild.log"
  fi
fi
exit "${status}"
