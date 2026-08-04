#!/usr/bin/env bash
# Sequential decode-probe sweep for the rows-per-simdgroup generalization study.
# Each arm restarts the worker so the geometry change is recompiled and the
# measurement is independent. Arms are ENV=VAL[,ENV=VAL] tokens; "base" means
# no override.
set -u

STEPS="${STEPS:-120}"
ARMS=("$@")
if [ "${#ARMS[@]}" -eq 0 ]; then
  echo "usage: sweep.sh ARM [ARM ...]" >&2
  exit 2
fi

for arm in "${ARMS[@]}"; do
  echo "===== ARM ${arm} ====="
  env_args=("STEPS=${STEPS}")
  if [ "${arm}" != "base" ]; then
    IFS=',' read -r -a pairs <<<"${arm}"
    for p in "${pairs[@]}"; do env_args+=("${p}"); done
  fi
  env "${env_args[@]}" python3 research/decode_probe.py --steps "${STEPS}" 2>&1 \
    | grep -E "decode steps=|divergen|seed forward"
  echo "===== END ${arm} ====="
done
