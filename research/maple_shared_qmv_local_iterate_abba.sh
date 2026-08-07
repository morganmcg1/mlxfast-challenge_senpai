#!/usr/bin/env bash
# Research-only (PR #301): end-to-end ABBA driver for the shared-expert NVFP4
# QMV arms over the trusted `./benchmark.sh --local-iterate` entrypoint.
#
#   ORDER="off on pairwise pairwise on off" REPS=1 OUT=/tmp/maple-stage3 \
#       bash research/maple_shared_qmv_local_iterate_abba.sh
#
# Arms are selected only through the model-side opt-in environment variables,
# so every run uses the same binary and the same trusted harness:
#
#   off       stock shared-expert QMV kernel
#   on        + K-block prefetch                (DARKBLOOM_SHARED_QMV_PREFETCH)
#   pairwise  + halved gate/up scale plane      (..._PAIRWISE_SCALES, implies
#                                                the prefetch arm)
#
# The default ORDER is palindromic, so each arm holds the same mean position in
# a repetition and a monotone host drift cannot favour one arm. The 40C cool
# gate is left enabled (only the interactive fan prompt is suppressed, which is
# what unattended automation is expected to do); each local-iterate re-gates
# before its prefill and decode phases.
set -uo pipefail

ORDER="${ORDER:-off on pairwise pairwise on off}"
REPS="${REPS:-1}"
OUT="${OUT:-/tmp/maple-shared-qmv-stage3}"
mkdir -p "${OUT}"

idx=0
for rep in $(seq 1 "${REPS}"); do
  for arm in ${ORDER}; do
    idx=$((idx + 1))
    tag=$(printf '%02d-rep%s-%s' "${idx}" "${rep}" "${arm}")
    # The fan-prompt suppression keeps this array non-empty, which matters for
    # the bash 3.2 that ships with macOS: under `set -u` an empty "${a[@]}" is
    # an unbound-variable error there.
    arm_env=(MLXFAST_LOCAL_FAN_PROMPT=0)
    case "${arm}" in
      off) ;;
      on) arm_env+=(DARKBLOOM_SHARED_QMV_PREFETCH=1) ;;
      pairwise)
        arm_env+=(DARKBLOOM_SHARED_QMV_PREFETCH=1
                  DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES=1) ;;
      *) echo "unknown arm ${arm}" >&2; exit 2 ;;
    esac
    rm -f score.local-iterate.json
    echo "=== ${tag} starting $(date -u +%H:%M:%SZ) ==="
    start=${SECONDS}
    env "${arm_env[@]}" \
      ./benchmark.sh --local-iterate > "${OUT}/${tag}.log" 2>&1
    rc=$?
    dur=$((SECONDS - start))
    if [[ -f score.local-iterate.json ]]; then
      cp score.local-iterate.json "${OUT}/${tag}.score.json"
    fi
    printf '%s rc=%s seconds=%s\n' "${tag}" "${rc}" "${dur}" | tee -a "${OUT}/summary.txt"
  done
done
