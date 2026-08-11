#!/usr/bin/env bash
# Capture the mandatory command-buffer environment readback for both startup memory
# profiles (auto and full) plus the resident-memory diagnostics, one process at a time.
set -uo pipefail

OUT="${OUT:-/tmp/r119b-envguard}"
STEPS="${STEPS:-8}"
mkdir -p "$OUT"

run_cell() {
  local tag="$1"
  local profile="$2"
  echo "=== cell ${tag} (DARKBLOOM_STARTUP_MEMORY_PROFILE=${profile:-<unset>}) ==="
  (
    export DARKBLOOM_ENV_READBACK=1
    if [[ -n "$profile" ]]; then
      export DARKBLOOM_STARTUP_MEMORY_PROFILE="$profile"
    else
      unset DARKBLOOM_STARTUP_MEMORY_PROFILE
    fi
    python3 research/decode_probe.py --steps "$STEPS" --prefill --stderr
  ) >"${OUT}/${tag}.log" 2>"${OUT}/${tag}.err"
  echo "exit=$?"
  grep -h -E 'ENVREADBACK|low-memory startup|worker up in|diagnostics after load|median=' \
    "${OUT}/${tag}.log" "${OUT}/${tag}.err" | sed "s/^/${tag}: /"
}

run_cell auto ""
run_cell full "full"
echo "ENVGUARD_DONE"
