#!/usr/bin/env bash
# Recover the one safetensors shard whose setup.sh download is cycling.
#
# Observed failure: setup.sh's per-shard curl uses --speed-limit 1048576
# --speed-time 120. The mirror's throughput decayed from 9.2 to 2.9 MiB/s, so
# the transfer trips that stall abort near completion; the wrapper's retry path
# then deletes the .partial and restarts from zero. Three full ~4.85 GiB cycles
# were lost this way (progress 98% -> 79% at 00:40, 01:00 and 01:20 elapsed).
#
# This fetcher keeps the same URL and hash but resumes instead of restarting,
# and tolerates a slow mirror (--speed-limit 65536).
set -uo pipefail

SNAP="${HOME}/.cache/huggingface/hub/models--poolside--Laguna-XS-2.1-NVFP4-mlx/snapshots/841778bda563a36104dd521e37d99218e46f4f25"
FILE="model-00004-of-00005.safetensors"
URL="https://ds4.darkbloom.ai/laguna-xs-2.1-nvfp4-mlx/${FILE}"
SHA="fdf825800be5ce39c414778d785ea8c3282d58b54550b5f8f99fc5a0177b928f"
SIZE=5205257850
PARTIAL="${SNAP}/${FILE}.partial"
FINAL="${SNAP}/${FILE}"

for attempt in $(seq 1 60); do
  have=0
  [[ -f "${PARTIAL}" ]] && have="$(wc -c < "${PARTIAL}" | tr -d ' ')"
  echo "$(date -u +%H:%M:%SZ) attempt=${attempt} have=${have}/${SIZE}"

  if [[ "${have}" -lt "${SIZE}" ]]; then
    curl --fail --location --continue-at - \
      --speed-limit 65536 --speed-time 300 \
      --retry 3 --retry-delay 10 \
      --silent --show-error \
      --output "${PARTIAL}" "${URL}" \
      && echo "$(date -u +%H:%M:%SZ) curl returned 0" \
      || echo "$(date -u +%H:%M:%SZ) curl returned $? (will resume)"
    continue
  fi

  if [[ "${have}" -gt "${SIZE}" ]]; then
    echo "$(date -u +%H:%M:%SZ) partial overshot expected size; restarting"
    rm -f "${PARTIAL}"
    continue
  fi

  echo "$(date -u +%H:%M:%SZ) size matches; verifying sha256"
  actual="$(shasum -a 256 "${PARTIAL}" | awk '{print $1}')"
  if [[ "${actual}" == "${SHA}" ]]; then
    mv "${PARTIAL}" "${FINAL}"
    echo "$(date -u +%H:%M:%SZ) VERIFIED and installed ${FINAL}"
    exit 0
  fi
  echo "$(date -u +%H:%M:%SZ) sha256 mismatch (${actual}); restarting from scratch"
  rm -f "${PARTIAL}"
done

echo "$(date -u +%H:%M:%SZ) EXHAUSTED attempts without a verified shard" >&2
exit 1
