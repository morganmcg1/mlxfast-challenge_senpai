#!/usr/bin/env bash
# Research-only (PR #457, R85-C): confirms the placement-dose arms are inert.
#
# `DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE` builds and retains N halved shared
# gate/up scale planes that no kernel reads, so every dose arm must produce the
# same self-fed token sequence as `base`. `halved` reads its plane, so it must
# also agree (that is PR #443's certified-equal claim). A free run accumulates
# any divergence, so matching hashes mean every step's argmax matched.
#
# Also greps the packed-scales log so an arm that silently declined to build the
# plane (uncertified checkpoint) cannot be mistaken for a null result.
#
#   OUT=/tmp/maple-r85-inert STEPS=24 \
#     bash research/maple_r85_dose_inertness.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-r85-inert}"
STEPS="${STEPS:-24}"
BOOTSTRAP="${BOOTSTRAP:-9081}"
mkdir -p "${OUT}"

for arm in ${ARMS:-base dose_one dose_two halved}; do
  unset DARKBLOOM_SHARED_SCALE_HALVED DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE \
    DARKBLOOM_SHARED_SCALE_PAD_PAGES
  case "${arm}" in
    base) : ;;
    dose_one) export DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE=1 ;;
    dose_two) export DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE=2 ;;
    halved) export DARKBLOOM_SHARED_SCALE_HALVED=1 ;;
    halved_pad)
      export DARKBLOOM_SHARED_SCALE_HALVED=1 \
        DARKBLOOM_SHARED_SCALE_PAD_PAGES="${PAD_PAGES:-5}" ;;
  esac
  echo "=== ${arm} ==="
  python3 research/decode_probe.py --steps "${STEPS}" --free-run \
    --free-run-bootstrap "${BOOTSTRAP}" \
    --dump-tokens "${OUT}/${arm}.tokens" \
    --stderr "${OUT}/${arm}.err" >"${OUT}/${arm}.log" 2>&1
  echo "exit=$?"
  grep -E "hash|halved scale plane" "${OUT}/${arm}.log" | head -4
done

echo
echo "===== token-sequence digests ====="
for arm in base dose_one dose_two halved; do
  printf "%-9s %s\n" "${arm}" "$(shasum -a 256 "${OUT}/${arm}.tokens" | cut -c1-16)"
done
