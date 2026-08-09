#!/usr/bin/env bash
# r97-d Stage 1: the primary measurement. Blocked-randomised ladder of the
# prefill-only work injector over the trusted `./benchmark.sh --local-iterate`
# entrypoint, which reproduces the official harness's decode timer topology
# (decodePhaseStart is taken BEFORE the 512-token seed forward).
#
#   RUNGS="0 8 16 32" BLOCKS=3 OUT=research/r97-runs/stage1 \
#       bash research/frieren_r97_stage1_local_iterate.sh
#
# Every arm runs the SAME binary; only DARKBLOOM_INJECT_PREFILL_MATMULS
# differs, so the submitted surface is unchanged by 0 bytes.
#
# Rungs are permuted independently inside each block from a fixed seed, so no
# rung holds a systematically early or late position and a monotone host drift
# cannot masquerade as a response to the injected work.
set -uo pipefail
cd "$(dirname "$0")/.."

RUNGS="${RUNGS:-0 8 16 32}"
BLOCKS="${BLOCKS:-3}"
SEED="${SEED:-93}"
OUT="${OUT:-research/r97-runs/stage1}"
# This host idles right on the 40 C gate threshold, so a run started
# immediately after the previous one stalls the gate instead of passing it.
PRECOOL_SECONDS="${PRECOOL_SECONDS:-120}"
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-2}"
mkdir -p "${OUT}"

SCHEDULE=$(python3 - "$RUNGS" "$BLOCKS" "$SEED" <<'PY'
import random, sys
rungs = [int(x) for x in sys.argv[1].split()]
blocks, seed = int(sys.argv[2]), int(sys.argv[3])
rng = random.Random(seed)
out = []
for b in range(blocks):
    blk = rungs[:]
    rng.shuffle(blk)
    out += [f"{b}:{n}" for n in blk]
print(" ".join(out))
PY
)
echo "schedule: ${SCHEDULE}" | tee "${OUT}/schedule.txt"

export PATH="${HOME}/.local/bin:${HOME}/bin:${PATH}"
export MLXFAST_MACMON_BIN="${MLXFAST_MACMON_BIN:-${HOME}/bin/macmon}"
export MLXFAST_GPU_TEMP_CMD="${MLXFAST_MACMON_BIN} pipe -s1 | jq -M -r '.temp.cpu_temp_avg'"
export MLXFAST_LOCAL_FAN_PROMPT=0

idx=0
consecutive_failures=0
for item in ${SCHEDULE}; do
  block="${item%%:*}"
  n="${item##*:}"
  idx=$((idx + 1))
  tag=$(printf '%02d-b%s-n%s' "${idx}" "${block}" "${n}")
  if [[ "${PRECOOL_SECONDS}" -gt 0 ]]; then
    echo "--- idling ${PRECOOL_SECONDS}s to soak-cool the chassis ---"
    sleep "${PRECOOL_SECONDS}"
  fi
  ./benchmark.sh --local-cool-gate-only >>"${OUT}/precool.log" 2>&1 || true
  rm -f score.local-iterate.json
  echo "=== ${tag} starting $(date -u +%H:%M:%SZ) ==="
  start=${SECONDS}
  DARKBLOOM_INJECT_PREFILL_MATMULS="${n}" \
    ./benchmark.sh --local-iterate >"${OUT}/${tag}.log" 2>&1
  rc=$?
  dur=$((SECONDS - start))
  if [[ -f score.local-iterate.json ]]; then
    cp score.local-iterate.json "${OUT}/${tag}.score.json"
  fi
  printf '%s rc=%s seconds=%s\n' "${tag}" "${rc}" "${dur}" | tee -a "${OUT}/summary.txt"
  grep -E "decode measured start|prefill measured start" "${OUT}/${tag}.log" | head -2
  if [[ "${rc}" -eq 0 ]]; then
    consecutive_failures=0
  else
    consecutive_failures=$((consecutive_failures + 1))
    if [[ "${consecutive_failures}" -ge "${MAX_CONSECUTIVE_FAILURES}" ]]; then
      echo "aborting: ${consecutive_failures} consecutive failed runs" \
        | tee -a "${OUT}/summary.txt"
      exit 3
    fi
  fi
done
echo "=== stage1 complete $(date -u +%H:%M:%SZ) ==="
