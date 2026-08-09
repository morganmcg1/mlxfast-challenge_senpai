#!/usr/bin/env bash
# Research-only (PR #558, R100-C): counterbalanced end-to-end A/B over the
# trusted `./benchmark.sh --local-iterate` entrypoint for the restored
# DARKBLOOM_ROUTER_WEIGHT_PREFETCH arms.
#
#   bash research/maple-nezuko-r100c-e2e-ab.sh OUTDIR REPS ARM [ARM...]
#
# ARM is the raw env value: 0 = unhoisted baseline, 1 = hoisted candidate
# (shipped default), 5 = character-identical placement control emitted below
# the normalize barrier. Every arm runs the same binary; only the JIT'd router
# pipeline differs, so there is no build-to-build confound.
#
# Because the runtime default is 1, the baseline leg MUST set the variable
# explicitly. This script always exports it, for every arm, including 1.
#
# Rule 75: the full Sources+Vendor digest is recorded before the first run and
# after the last one, so a mid-sweep source edit cannot be mistaken for drift.
#
# The 40C cool gate stays enabled; only the interactive fan prompt is
# suppressed. A single arm and REPS=1 is the pilot/correctness invocation.
set -uo pipefail

OUT="${1:?usage: OUTDIR REPS ARM [ARM...]}"
REPS="${2:?usage: OUTDIR REPS ARM [ARM...]}"
shift 2
ORDER=("$@")
[ "${#ORDER[@]}" -gt 0 ] || { echo "no arms given" >&2; exit 2; }

PRECOOL_SECONDS="${PRECOOL_SECONDS:-0}"
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-2}"
mkdir -p "${OUT}"

tree_digest() {
  find Sources Vendor -type f -print0 | sort -z | xargs -0 shasum -a 256 \
    | shasum -a 256 | awk '{print $1}'
}

printf 'head=%s\n' "$(git rev-parse HEAD)" | tee "${OUT}/provenance.txt"
printf 'digest_before=%s\n' "$(tree_digest)" | tee -a "${OUT}/provenance.txt"
printf 'dirty=%s\n' "$(git status --porcelain | wc -l | tr -d ' ')" \
  | tee -a "${OUT}/provenance.txt"

idx=0
consecutive_failures=0
for rep in $(seq 1 "${REPS}"); do
  for arm in "${ORDER[@]}"; do
    idx=$((idx + 1))
    if [ "${PRECOOL_SECONDS}" -gt 0 ]; then
      echo "--- idling ${PRECOOL_SECONDS}s to soak-cool the chassis ---"
      sleep "${PRECOOL_SECONDS}"
    fi
    tag=$(printf '%02d-rep%s-pf%s' "${idx}" "${rep}" "${arm}")
    rm -f score.local-iterate.json
    echo "=== ${tag} starting $(date -u +%H:%M:%SZ) ==="
    start=${SECONDS}
    env MLXFAST_LOCAL_FAN_PROMPT=0 \
        DARKBLOOM_ROUTER_WEIGHT_PREFETCH="${arm}" \
      ./benchmark.sh --local-iterate > "${OUT}/${tag}.log" 2>&1
    rc=$?
    dur=$((SECONDS - start))
    if [ -f score.local-iterate.json ]; then
      cp score.local-iterate.json "${OUT}/${tag}.score.json"
    fi
    printf '%s rc=%s seconds=%s\n' "${tag}" "${rc}" "${dur}" \
      | tee -a "${OUT}/summary.txt"
    grep -E "seconds_per_token|speedup|max_abs_diff|mismatch" \
      "${OUT}/${tag}.score.json" 2>/dev/null | tee -a "${OUT}/summary.txt"
    if [ "${rc}" -eq 0 ]; then
      consecutive_failures=0
    else
      consecutive_failures=$((consecutive_failures + 1))
      tail -40 "${OUT}/${tag}.log" | tee -a "${OUT}/summary.txt"
      if [ "${consecutive_failures}" -ge "${MAX_CONSECUTIVE_FAILURES}" ]; then
        echo "aborting: ${consecutive_failures} consecutive failed runs" \
          | tee -a "${OUT}/summary.txt"
        printf 'digest_after=%s\n' "$(tree_digest)" \
          | tee -a "${OUT}/provenance.txt"
        exit 3
      fi
    fi
  done
done

printf 'digest_after=%s\n' "$(tree_digest)" | tee -a "${OUT}/provenance.txt"
echo "########## done ##########"
