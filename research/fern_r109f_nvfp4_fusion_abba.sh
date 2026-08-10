#!/usr/bin/env bash
# R109-F priority probe: is the dead `lagunaNormAffineQKV` fusion worth implementing?
#
# The advisor's one-env-var probe (DARKBLOOM_NATIVE_AFFINE_NVFP4=0) bundles the
# fusion gain with a NVFP4->INT8 representation change on BOTH the QKV and the
# o_proj banks plus three kernel-selection flips, so its delta is not
# attributable. A third arm holds the quantization fixed and turns only the
# fusion off, which makes the fusion gain a difference of differences:
#
#   A  default                                     NVFP4 bank, fusion dead
#   B  NATIVE_AFFINE_NVFP4=0                       INT8 bank, fusion live
#   C  NATIVE_AFFINE_NVFP4=0 FUSED_NORM_AFFINE_QKV=0  INT8 bank, fusion dead
#
#   C - A = cost of the NVFP4 -> INT8 representation change (confound)
#   B - C = the fusion gain at matched quantization  <-- the number wanted
#   B - A = the advisor's bundled probe (reported for continuity)
#
# Arms B and C are numerically different from default and are NOT submittable;
# they exist only to price the mechanism. Correctness is expected to fail on
# them, which is why this script does not stop on a non-zero benchmark exit.
set -uo pipefail
cd "$(dirname "$0")/.."

OUT="research/artifacts/fern-r109f/nvfp4-fusion"
mkdir -p "${OUT}"
ORDER=${ORDER:-"W B C"}
TAG=${TAG:-pilot}

for slot_arm in ${ORDER}; do
  case "${slot_arm}" in
    W | A) unset DARKBLOOM_NATIVE_AFFINE_NVFP4 DARKBLOOM_FUSED_NORM_AFFINE_QKV ;;
    B)
      export DARKBLOOM_NATIVE_AFFINE_NVFP4=0
      unset DARKBLOOM_FUSED_NORM_AFFINE_QKV
      ;;
    C)
      export DARKBLOOM_NATIVE_AFFINE_NVFP4=0
      export DARKBLOOM_FUSED_NORM_AFFINE_QKV=0
      ;;
    *)
      echo "unknown arm '${slot_arm}'" >&2
      exit 2
      ;;
  esac

  n=$(ls "${OUT}"/${TAG}-*.json 2>/dev/null | wc -l | tr -d ' ')
  slot=$(printf '%02d' $((n + 1)))
  stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "=== ${TAG} slot ${slot} arm ${slot_arm} start ${stamp} ==="
  MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-iterate \
    >"${OUT}/${TAG}-${slot}-${slot_arm}.log" 2>&1
  rc=$?
  echo "=== ${TAG} slot ${slot} arm ${slot_arm} rc=${rc} end $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  if [ -f score.local-iterate.json ]; then
    python3 - "${OUT}/${TAG}-${slot}-${slot_arm}.json" "${slot_arm}" "${rc}" \
      "${stamp}" <<'PY'
import json, shutil, sys
dest, arm, rc, stamp = sys.argv[1:5]
shutil.copyfile("score.local-iterate.json", dest)
d = json.load(open(dest))
m = d.get("metrics", {})
rec = {
    "arm": arm, "rc": int(rc), "started": stamp,
    "decode_s_per_tok": m.get("decode_seconds_per_token"),
    "prefill_s_per_tok": m.get("prefill_seconds_per_token"),
    "score": d.get("score"), "passed": d.get("passed"),
    "passed_correctness": m.get("passed_correctness"),
    "checked_steps": m.get("checked_steps"), "error": m.get("error"),
}
print(json.dumps(rec))
PY
  else
    echo "{\"arm\": \"${slot_arm}\", \"rc\": ${rc}, \"error\": \"no score.local-iterate.json\"}"
  fi
done
