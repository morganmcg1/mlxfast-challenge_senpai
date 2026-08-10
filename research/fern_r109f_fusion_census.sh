#!/usr/bin/env bash
# Structural dispatch census for the dead INT8 fusion suite (R109-F, advisor
# request 5 §3).  Zero source change: DARKBLOOM_TRACE_FUSION=1 makes
# lagunaTrace() (LagunaRuntimeModel.swift:93) emit one
# "mlxfast: fusion active: <site>" line per distinct dispatch site.
#
# Arms:
#   A  default                                        NVFP4 QKV/o_proj bank
#   B  DARKBLOOM_NATIVE_AFFINE_NVFP4=0                INT8 g32 bank, fusion live
#   C  B + DARKBLOOM_FUSED_NORM_AFFINE_QKV=0          INT8 g32 bank, fusion dead
#
# No timing claim is made here; --local-iterate is used only because it is the
# cheapest invocation that exercises the real prepareFusedRuntimeWeights path.
set -uo pipefail

OUT_DIR="research/artifacts/fern-r109f/census"
ORDER="${ORDER:-A B C}"
mkdir -p "${OUT_DIR}"

export MLXFAST_LOCAL_FAN_PROMPT=0
export DARKBLOOM_TRACE_FUSION=1

for arm in ${ORDER}; do
  log="${OUT_DIR}/census-${arm}.log"
  sites="${OUT_DIR}/sites-${arm}.txt"
  echo "=== census arm ${arm} -> ${log} ==="
  case "${arm}" in
    A) env -u DARKBLOOM_NATIVE_AFFINE_NVFP4 -u DARKBLOOM_FUSED_NORM_AFFINE_QKV \
         ./benchmark.sh --local-iterate >"${log}" 2>&1 ;;
    B) env -u DARKBLOOM_FUSED_NORM_AFFINE_QKV DARKBLOOM_NATIVE_AFFINE_NVFP4=0 \
         ./benchmark.sh --local-iterate >"${log}" 2>&1 ;;
    C) env DARKBLOOM_NATIVE_AFFINE_NVFP4=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0 \
         ./benchmark.sh --local-iterate >"${log}" 2>&1 ;;
    *) echo "unknown arm ${arm}" >&2; exit 2 ;;
  esac
  rc=$?
  grep -h 'fusion active:' "${log}" | sed 's/.*fusion active: //' | sort -u >"${sites}"
  echo "arm=${arm} rc=${rc} distinct_sites=$(wc -l <"${sites}" | tr -d ' ')"
done

echo
echo "=== census diff ==="
for arm in ${ORDER}; do
  printf '%-4s %s\n' "${arm}" "${OUT_DIR}/sites-${arm}.txt"
done
python3 research/fern_r109f_fusion_census_diff.py ${ORDER}
