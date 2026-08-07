#!/usr/bin/env bash
# Offline MSL compile check for the _nax expert gather-QMM JIT source.
#
# M4 hosts report Apple GPU generation 16 and never select the `_nax` kernels,
# so the JIT source below is not compiled by any local benchmark run. This
# script reproduces get_qmm_nax_kernel()'s concatenation order from
# Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp and hands
# the result to the offline Metal compiler, which is the only local way to catch
# a syntax or semantic error before an official M5 submission.
#
# Usage: research/nax_msl_compile_check.sh [NAME|NAME=VALUE ...]
#   GEN_DIR=<dir>  override the mlx-generated directory (for stock comparison)
#   OUT_DIR=<dir>  override the scratch output directory
#   BK=<n>         k-tile depth template arg (default 64)
#   PROBE=<n>      regime-discriminator template arg (default 0 = shipped)
#   PF=<n>         k-loop prefetch depth template arg (default 0 = shipped).
#                  PF>0 needs the PR #215 arm header, which was reverted after
#                  the arm was measured and closed; it will not compile on the
#                  frontier. Kept so the Step-0 table stays reproducible.
#   EMIT_LIB=1     also link a .metallib so pipeline stats can be read back
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="${GEN_DIR:-${REPO_ROOT}/Vendor/mlx-swift/Source/Cmlx/mlx-generated}"
BK="${BK:-64}"
PROBE="${PROBE:-0}"
PF="${PF:-0}"
OUT="${OUT_DIR:-/tmp/nax_msl_check}"
mkdir -p "${OUT}"

extract() {
  # Pull the body out of `const char* name() { return R"preamble( ... )preamble"; }`
  awk '
    /R"preamble\(/ { inb = 1; next }
    /^\)preamble";?$/ { inb = 0; next }
    inb { print }
  ' "$1"
}

SRC="${OUT}/unit.metal"
: > "${SRC}"
{
  echo "// ---- injected defines ----"
  for d in "$@"; do
    case "${d}" in
      *=*) echo "#define ${d%%=*} ${d#*=}" ;;
      *) echo "#define ${d} 1" ;;
    esac
  done
  echo "// ---- metal::utils() ----"
  extract "${GEN}/utils.cpp"
  echo "// ---- metal::gemm_nax() ----"
  extract "${GEN}/gemm_nax.cpp"
  echo "// ---- metal::quantized_utils() ----"
  extract "${GEN}/quantized_utils.cpp"
  echo "// ---- metal::fp_quantized_nax() ----"
  extract "${GEN}/fp_quantized_nax.cpp"
  # Both static Laguna MoE shapes (laguna_moe_shape in quantized.cpp), with the
  # shipped variant-5 tiling (bm/bn/bk 64, wm 4, wn 1), egroups 256 and both
  # wide-staging certifications on, exactly as get_template_definition emits.
  echo "// ---- template_def (get_template_definition) ----"
  # PROBE=0 emits neither the trailing argument nor a name suffix, exactly as
  # quantized.cpp does, so a probe-capable tree and a pre-probe tree produce
  # byte-identical AIR for the shipped kernel (safety-rig inertness check 2).
  for shape in "2048, 1024" "512, 2048"; do
    targs="bfloat16_t, 16, 4, 64, 64, ${BK}, 4, 1, true, ${shape}, bfloat, 256, true, true"
    name="fp_gather_qmm_rhs_expert_nax_check_${shape//, /x}_bk${BK}"
    if [ "${PROBE}" != "0" ] || [ "${PF}" != "0" ]; then
      targs="${targs}, ${PROBE}"
      [ "${PROBE}" != "0" ] && name="${name}_pb${PROBE}"
    fi
    if [ "${PF}" != "0" ]; then
      targs="${targs}, ${PF}"
      name="${name}_pf${PF}"
    fi
    cat <<EOF
template [[host_name("${name}")]] [[kernel]] decltype(
    fp_gather_qmm_rhs_expert_nax<${targs}>)
    fp_gather_qmm_rhs_expert_nax<${targs}>;
EOF
  done
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
    echo "METALLIB OK -> ${OUT}/unit.metallib"
  else
    echo "metallib link failed:"; head -15 "${OUT}/metallib.log"; status=1
  fi
fi

if [ "${status}" -eq 0 ] && [ "${EMIT_IR:-0}" = "1" ]; then
  if xcrun -sdk macosx metal -x metal -std=metal4.0 -Wno-c++17-extensions \
      -Wno-c++20-extensions -fno-fast-math -S -emit-llvm "${SRC}" \
      -o "${OUT}/unit.ll" > "${OUT}/emitir.log" 2>&1; then
    echo "IR OK -> ${OUT}/unit.ll"
  else
    echo "IR emit failed:"; head -15 "${OUT}/emitir.log"; status=1
  fi
fi
exit "${status}"
