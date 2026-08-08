#!/usr/bin/env bash
# Research-only (PR #443): byte-level verifier for the halved shared gate/up
# scale plane.
#
# The PR #443 fault battery showed the teacher-forced tripwire does not resolve
# `plane_byte`, `plane_column` or `header_drop`, so a 0-divergence token result
# alone cannot certify the halved plane at byte granularity. This driver runs
# the detector the tripwire is not: for every one of the 39 layers it
# reconstructs all 1024x128 group-16 scale bytes the *default* kernel reads out
# of the halved plane the *candidate* kernel reads -- group-32 byte for the lane
# pair, overridden by the 128-byte patch header at the two allow-listed first
# pairs -- and counts byte mismatches.
#
# Expected: 0 mismatches per layer in the clean arm, and >= 1 mismatch in every
# plane-fault arm, which bounds the detector's sensitivity at exactly one byte.
#
# Plane faults are read from the environment at plane-construction time, so all
# arms share one build. `header_drop` is a consumer-side fault and by
# construction leaves the plane bytes correct; it is not part of this ladder.
#
#   OUT=/tmp/maple-pr443-verify bash research/maple_pr443_plane_verify.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-pr443-verify}"
STEPS="${STEPS:-1}"
mkdir -p "${OUT}"
SUMMARY="${OUT}/summary.txt"
: >"${SUMMARY}"

ARMS=("clean:" "fault-plane_byte:plane_byte" "fault-plane_column:plane_column"
      "fault-plane_shift:plane_shift")

build_worker() {
  echo "### building worker ($1)"
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null || true
  return "${rc}"
}

cleanup() {
  echo "### reverting fault hooks"
  python3 research/maple_pr443_fault_injection.py revert
  build_worker "clean" || echo "WARNING: clean rebuild failed; rebuild before timing"
}

if ! git diff --quiet -- Sources/MLXFastModel/LagunaRuntimeModel.swift \
     Sources/MLXFastModel/LagunaRuntimeWeights.swift; then
  echo "refusing: patched sources are dirty; commit or stash first" >&2
  exit 2
fi

trap cleanup EXIT
python3 research/maple_pr443_fault_injection.py apply | tee "${OUT}/patch.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || exit 3
python3 research/maple_pr443_fault_injection.py check | tee -a "${OUT}/patch.log"
build_worker "faulted" || exit 4

index=0
for spec in "${ARMS[@]}"; do
  index=$((index + 1))
  label="${spec%%:*}"
  fault="${spec#*:}"
  tag="$(printf '%02d' "${index}")-${label}"

  env DARKBLOOM_SHARED_SCALE_HALVED=1 \
      DARKBLOOM_SHARED_PLANE_VERIFY=1 \
      DARKBLOOM_SHARED_QMV_FAULT="${fault}" \
      python3 research/decode_probe.py --steps "${STEPS}" \
        --stderr "${OUT}/${tag}.err" >"${OUT}/${tag}.log" 2>&1
  rc="${PIPESTATUS[0]}"

  cat "${OUT}/${tag}.err" "${OUT}/${tag}.log" 2>/dev/null \
    | grep 'plane-verify' >"${OUT}/${tag}.verify"
  sort -u "${OUT}/${tag}.verify" >"${OUT}/${tag}.verify.uniq"
  layers="$(wc -l <"${OUT}/${tag}.verify" | tr -d ' ')"
  worst="$(grep -o 'mismatches=[0-9]*' "${OUT}/${tag}.verify" \
    | cut -d= -f2 | sort -n | tail -1)"
  best="$(grep -o 'mismatches=[0-9]*' "${OUT}/${tag}.verify" \
    | cut -d= -f2 | sort -n | head -1)"
  echo "${tag} rc=${rc} layers=${layers:-0} min_mismatches=${best:-NA} max_mismatches=${worst:-NA}" \
    | tee -a "${SUMMARY}"
done

echo
echo "===== PR #443 halved-plane byte verification ====="
cat "${SUMMARY}"
echo
echo "--- distinct clean-arm verify lines ---"
cat "${OUT}/01-clean.verify.uniq" 2>/dev/null
