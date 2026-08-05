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
# Usage: research/nax_msl_compile_check.sh [DEFINE_NAME...]
#   GEN_DIR=<dir>  override the mlx-generated directory (for stock comparison)
#   OUT_DIR=<dir>  override the scratch output directory
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="${GEN_DIR:-${REPO_ROOT}/Vendor/mlx-swift/Source/Cmlx/mlx-generated}"
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
  for d in "$@"; do echo "#define ${d} 1"; done
  echo "// ---- metal::utils() ----"
  extract "${GEN}/utils.cpp"
  echo "// ---- metal::gemm_nax() ----"
  extract "${GEN}/gemm_nax.cpp"
  echo "// ---- metal::quantized_utils() ----"
  extract "${GEN}/quantized_utils.cpp"
  echo "// ---- metal::fp_quantized_nax() ----"
  extract "${GEN}/fp_quantized_nax.cpp"
  echo "// ---- template_def (get_template_definition) ----"
  cat <<'EOF'
template [[host_name("fp_gather_qmm_rhs_expert_nax_check")]] [[kernel]] decltype(
    fp_gather_qmm_rhs_expert_nax<
        bfloat16_t, 16, 4, 64, 64, 64, 4, 1, true, 2048, 1408, bfloat, 256, true, true>)
    fp_gather_qmm_rhs_expert_nax<
        bfloat16_t, 16, 4, 64, 64, 64, 4, 1, true, 2048, 1408, bfloat, 256, true, true>;
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
exit "${status}"
