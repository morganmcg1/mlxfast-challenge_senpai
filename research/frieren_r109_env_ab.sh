#!/bin/bash
# r109-A pivot: blocked paired timing over an arbitrary set of environment arms.
#
# Generalises research/frieren_r109_paired_ab.sh, which could only vary
# DARKBLOOM_DECODE_ASYNC_STAGE. Here each arm carries its own comma-separated
# list of VAR=VALUE assignments, so the router rowsPerGroup dial
# (DARKBLOOM_ROUTER_ROWS_PER_GROUP, LRM:675-684, default 8, accepts
# {1,2,4,8,16,32,64}) and the weight-prefetch dial
# (DARKBLOOM_ROUTER_WEIGHT_PREFETCH, LRM:696-703, default 1, accepts {0,1,5})
# can share one paired design.
#
# Both dials reach the worker through the LagunaRuntimeWorker environment
# allowlist (Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:1993-2023,
# DARKBLOOM_ prefix), and all 21 kernel variants are compiled at startup by
# lagunaResidualRMSNormRouterKernels (LRM:1119-1146), so no rebuild is needed.
#
#   research/frieren_r109_env_ab.sh [BLOCKS]
#
# Env:
#   ARMS_SPEC       space-separated "name|VAR=VAL[;VAR=VAL...]" items (";" separates
#                   assignments so comma-bearing values such as a decode mask
#                   "at:0,7" can be passed verbatim)
#                   (first item is the control for the analysis)
#   OUT             output dir (default research/r109-cadence/env-ab)
#   DEADLINE_EPOCH  do not START a new run at/after this unix time (0 = none)
#   BLOCK_OFFSET    first block index is BLOCK_OFFSET+1, so a follow-on job can
#                   append to the same results file without colliding block ids
set -u
cd "$(dirname "$0")/.." || exit 1

BLOCKS="${1:-4}"
OUT="${OUT:-research/r109-cadence/env-ab}"
DEADLINE_EPOCH="${DEADLINE_EPOCH:-0}"
BLOCK_OFFSET="${BLOCK_OFFSET:-0}"
ARMS_SPEC="${ARMS_SPEC:-ctl|DARKBLOOM_ROUTER_ROWS_PER_GROUP=8}"
mkdir -p "${OUT}"
RESULTS="${OUT}/results.jsonl"

read -r -a ARMS <<<"${ARMS_SPEC}"

run_arm() {
    local name="$1" assigns="$2" block="$3" slot="$4"
    local score="${OUT}/score-${name}-b${block}.json"
    local log="${OUT}/log-${name}-b${block}.txt"
    local t0 t1 status
    local -a envargs=()
    local kv
    local IFS=';'
    for kv in ${assigns}; do envargs+=("${kv}"); done
    unset IFS

    t0=$(date +%s)
    env "${envargs[@]}" MLXFAST_SCORE_PATH="${score}" \
        ./benchmark.sh --local-iterate >"${log}" 2>&1
    status=$?
    t1=$(date +%s)
    echo "@@RUN block=${block} slot=${slot} arm=${name} assigns=${assigns} exit=${status} secs=$((t1 - t0))"
    grep -c "low-memory startup profile active" "${log}" \
        | sed "s/^/@@LOWMEM_NOTICES ${name} b${block} /"

    jq -c --arg arm "${name}" --arg value "${assigns}" \
        --argjson block "${block}" --argjson slot "${slot}" \
        --argjson exit "${status}" --argjson secs "$((t1 - t0))" \
        --argjson t0 "${t0}" \
        '{arm:$arm, value:$value, block:$block, slot:$slot,
          exit:$exit, wall_secs:$secs, started:$t0,
          score:.score,
          decode_spt:.metrics.decode_seconds_per_token,
          prefill_spt:.metrics.prefill_seconds_per_token,
          decode_speedup:.metrics.decode_speedup,
          prefill_speedup:.metrics.prefill_speedup,
          passed_correctness:.metrics.passed_correctness,
          golden_hash:.metrics.golden_hash,
          first_failing_case:.metrics.first_failing_case,
          first_failing_step:.metrics.first_failing_step}' \
        "${score}" >>"${RESULTS}" 2>/dev/null \
        || echo "{\"arm\":\"${name}\",\"value\":\"${assigns}\",\"block\":${block},\"slot\":${slot},\"exit\":${status},\"wall_secs\":$((t1 - t0)),\"started\":${t0},\"score\":null}" >>"${RESULTS}"
}

for ((b = BLOCK_OFFSET + 1; b <= BLOCK_OFFSET + BLOCKS; b++)); do
    echo "@@BLOCK ${b} start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    order=()
    if ((b % 2 == 1)); then
        for ((i = 0; i < ${#ARMS[@]}; i++)); do order+=("${ARMS[i]}"); done
    else
        for ((i = ${#ARMS[@]} - 1; i >= 0; i--)); do order+=("${ARMS[i]}"); done
    fi
    slot=0
    for item in "${order[@]}"; do
        slot=$((slot + 1))
        if ((DEADLINE_EPOCH > 0)) && (($(date +%s) >= DEADLINE_EPOCH)); then
            echo "@@DEADLINE reached before block=${b} slot=${slot}; stopping"
            exit 0
        fi
        run_arm "${item%%|*}" "${item#*|}" "${b}" "${slot}"
    done
done
echo "@@DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)"
