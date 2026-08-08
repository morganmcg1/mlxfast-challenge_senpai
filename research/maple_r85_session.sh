#!/usr/bin/env bash
# Research-only (PR #457, R85-C): one session = inertness gate, then timing.
#
# The four-arm timing run costs ~50 minutes, and a placement arm that silently
# declined to build its plane, or that perturbed a read byte, would make every
# number in it meaningless. So the free-run digests are checked first and the
# timing run starts only if all four arms agree with `base`.
#
#   bash research/maple_r85_session.sh
set -uo pipefail

INERT_OUT="${INERT_OUT:-/tmp/maple-r85-inert}"
ARMS_OUT="${ARMS_OUT:-/tmp/maple-r85-arms}"

echo "##################### stage 1: dose inertness #####################"
OUT="${INERT_OUT}" bash research/maple_r85_dose_inertness.sh || exit 10

ref=""
for arm in ${ARMS:-base dose_one dose_two halved}; do
  digest=$(shasum -a 256 "${INERT_OUT}/${arm}.tokens" 2>/dev/null | cut -d' ' -f1)
  if [ -z "${digest}" ]; then
    echo "refusing: ${arm} produced no token dump" >&2
    exit 11
  fi
  if [ -z "${ref}" ]; then
    ref="${digest}"
  elif [ "${digest}" != "${ref}" ]; then
    echo "refusing: ${arm} token sequence diverged from base" >&2
    exit 12
  fi
done
echo "inertness gate PASSED: all four arms share one token sequence"

echo "##################### stage 2: placement arms #####################"
OUT="${ARMS_OUT}" bash research/maple_r85_placement_arms.sh
echo "stage 2 exit=$?"
