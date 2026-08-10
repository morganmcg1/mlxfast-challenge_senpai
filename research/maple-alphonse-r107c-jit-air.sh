#!/usr/bin/env bash
# R107-C static instantiation ledger for fp_gather_qmm_rhs_expert_nax.
#
# Reconstructs the exact runtime JIT translation unit that
# get_qmm_nax_kernel() assembles (mlx-generated preambles + the darkbloom
# defines + one get_template_definition line, compiled -std=metal4.0 with
# fast math off, as device.cpp does) and compiles it offline with
# `xcrun metal` for a list of BN values.
#
# This is a STATIC ledger, not a timing measurement: this host is an M4 Pro
# (Apple GPU generation 16), so metal::is_nax_available() is false and the
# kernel is unreachable at runtime here. Offline AIR compilation does not
# need the GPU, so instantiation validity, threadgroup-memory footprint,
# MMA-instruction count, staging access widths and control flow can all be
# read off the AIR even though no dispatch is possible.
#
# Usage: research/maple-alphonse-r107c-jit-air.sh [BN ...]      (default 64 32)
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null && pwd -P)"
cd "${ROOT_DIR}"

OUT_DIR="${OUT_DIR:-research/artifacts/maple-alphonse-r107c}"
GEN="Vendor/mlx-swift/Source/Cmlx/mlx-generated"
mkdir -p "${OUT_DIR}"

BNS=("$@")
if [[ ${#BNS[@]} -eq 0 ]]; then
  BNS=(64 32)
fi

# Rule 75: digest the whole submitted-surface source set before and after.
digest() {
  find Sources Vendor -type f \
    \( -name '*.swift' -o -name '*.metal' -o -name '*.h' -o -name '*.cpp' \) \
    | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256 | awk '{print $1}'
}
DIGEST_PRE="$(digest)"
echo "surface-digest-pre ${DIGEST_PRE}"

extract() {
  # Pull the R"preamble( ... )preamble" body out of a generated JIT source.
  python3 - "$1" <<'PY'
import sys
src = open(sys.argv[1]).read()
start = src.index('R"preamble(') + len('R"preamble(')
end = src.index(')preamble"', start)
sys.stdout.write(src[start:end])
PY
}

PRE="${OUT_DIR}/jit-preamble.metal"
{
  extract "${GEN}/utils.cpp"
  # Runtime defaults on this base: STAGE2_GATHER off, GATHER_XMAJOR off
  # (darkbloom_gather_xmajor_ct() returns 0), SWIGLU_REGLOCAL on,
  # BSEARCH_HOIST on.
  printf '\n#define DARKBLOOM_SWIGLU_REGLOCAL 1\n'
  printf '\n#define DARKBLOOM_BSEARCH_HOIST 1\n'
  extract "${GEN}/gemm_nax.cpp"
  extract "${GEN}/quantized_utils.cpp"
  extract "${GEN}/fp_quantized_nax.cpp"
} > "${PRE}"
echo "preamble ${PRE} $(wc -l < "${PRE}") lines"

# The generated twin is what the JIT actually compiles; if it has drifted from
# the editable header the ledger would describe the wrong kernel.
if ! diff -q <(extract "${GEN}/fp_quantized_nax.cpp" \
                 | sed '/^\/\/ Auto generated source/d') \
             <(sed -e '1,2d' \
                 Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h) \
             >/dev/null 2>&1; then
  echo "note: generated twin is not a byte-identical tail of the header;" \
       "see ${OUT_DIR}/twin-diff.txt"
  diff <(extract "${GEN}/fp_quantized_nax.cpp") \
       Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h \
       > "${OUT_DIR}/twin-diff.txt" || true
fi

# Down projection (K=512, N=2048): pairwise scale layout 2, non-fused
# epilogue. Template order mirrors the quantized.cpp call site exactly.
for BN in "${BNS[@]}"; do
  SRC="${OUT_DIR}/down-bn${BN}.metal"
  AIR="${OUT_DIR}/down-bn${BN}.air"
  LOG="${OUT_DIR}/down-bn${BN}.compile.log"
  NAME="nvfp4_gather_qmm_rhs_expert_static_nax_nt_bfloat16_t_gs_16_b_4_bm_64_bn_${BN}_bk_64_wm_4_wn_1_k_512_n_2048_eg_256_ws_1_wl_1_ps_2"
  {
    cat "${PRE}"
    printf '\ntemplate [[host_name("%s")]] [[kernel]] decltype(%s) %s;\n' \
      "${NAME}" \
      "fp_gather_qmm_rhs_expert_nax<bfloat16_t, 16, 4, 64, ${BN}, 64, 4, 1, 1, 512, 2048, bfloat, 256, 1, 1, 2>" \
      "fp_gather_qmm_rhs_expert_nax<bfloat16_t, 16, 4, 64, ${BN}, 64, 4, 1, 1, 512, 2048, bfloat, 256, 1, 1, 2>"
  } > "${SRC}"
  if xcrun metal -std=metal4.0 -fno-fast-math -c "${SRC}" -o "${AIR}" \
       > "${LOG}" 2>&1; then
    echo "compile BN=${BN} ok air_bytes=$(wc -c < "${AIR}" | tr -d ' ')"
  else
    echo "compile BN=${BN} FAILED (see ${LOG})"
    tail -20 "${LOG}"
  fi
done

DIGEST_POST="$(digest)"
echo "surface-digest-post ${DIGEST_POST}"
if [[ "${DIGEST_PRE}" != "${DIGEST_POST}" ]]; then
  echo "ABORT: submitted-surface digest drifted during the run (rule 75)" >&2
  exit 3
fi
