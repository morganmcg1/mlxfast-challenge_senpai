#!/usr/bin/env bash

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW_DIR="${ROOT}/.agent_tmp/oproj-scale-census-raw"
CAPTURE="${ROOT}/.agent_tmp/oproj-scale-census.stderr"

rm -rf "${RAW_DIR}"
mkdir -p "$(dirname "${CAPTURE}")"
rm -f "${CAPTURE}"

export DARKBLOOM_OPROJ_CENSUS=1
status=0
"${ROOT}/benchmark.sh" --local-iterate 2>"${CAPTURE}" || status=$?
grep -v 'OPROJ_CENSUS ' "${CAPTURE}" >&2 || true
if [[ "${status}" -eq 0 ]]; then
  python3 "${ROOT}/research/oproj_scale_census.py" \
    --extract-stderr "${CAPTURE}" \
    --raw-dir "${RAW_DIR}" || status=$?
fi
if [[ "${status}" -eq 0 ]]; then
  rm -f "${CAPTURE}"
else
  echo "oproj census: retained failed stderr capture at ${CAPTURE}" >&2
fi
exit "${status}"
