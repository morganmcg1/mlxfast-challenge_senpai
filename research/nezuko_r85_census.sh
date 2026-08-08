#!/usr/bin/env bash
# R85-D profiled census: dispatch + command-buffer counts at every ladder rung.
# Settles (i) elision of the injected ops and (ii) the CB-repacking confound.
#   bash /tmp/r85/census.sh /tmp/r85/census [STEPS]
set -uo pipefail
OUT="${1:?outdir}"
STEPS="${2:-40}"
mkdir -p "${OUT}"

for arm in w0 w8 w16 w32 w64 t0 t8 t16 t32 t64; do
  case "${arm:0:1}" in w) mode=wide ;; t) mode=tiny ;; esac
  k="${arm:1}"
  echo "=== $(date -u +%H:%M:%S) ${arm} mode=${mode} k=${k}"
  DARKBLOOM_GPU_PROFILE=1 \
  DARKBLOOM_R85_LADDER_MODE="${mode}" \
  DARKBLOOM_R85_LADDER_K="${k}" \
  python3 research/decode_probe.py --steps "${STEPS}" --profile \
    > "${OUT}/${arm}.log" 2>&1
  grep -E "divergence|per steady step" "${OUT}/${arm}.log" | head -3
done
echo "=== $(date -u +%H:%M:%S) census done"
