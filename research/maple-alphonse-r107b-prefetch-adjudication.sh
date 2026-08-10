#!/usr/bin/env bash
# Research-only driver for round-107 arm B: does the shipped depth-1 preload in
# the routed gate/up R1 kernel pay for itself?
#
# Reuses `research/fern_r99_qmv_probe.swift` unchanged (Rule 58).  The probe
# alternates reference/variant order every round, so even-indexed per-round
# deltas are reference-first and odd-indexed are variant-first; the analysis
# step splits them to report order sensitivity.
#
#   research/maple-alphonse-r107b-prefetch-adjudication.sh
#
# Writes logs to research/artifacts/maple-alphonse-r107b/.

set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OUT="research/artifacts/maple-alphonse-r107b"
PROBE=/tmp/maple_r107b_qmv
PY="${PY:-python3}"

ROUNDS="${ROUNDS:-32}"
REPS="${REPS:-500}"
DEFEAT_SLOTS="${DEFEAT_SLOTS:-64}"

digest() {
  # Rule 75: the timed tree must be pinned before and after the run.
  find Sources Vendor -type f \( -name '*.swift' -o -name '*.metal' -o -name '*.h' \
    -o -name '*.cpp' \) -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256
}

mkdir -p "${OUT}"

{
  echo "=== provenance ==="
  echo "utc            $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host           $(sysctl -n machdep.cpu.brand_string)"
  echo "git head       $(git rev-parse HEAD)"
  echo "git status     $(git status --porcelain | wc -l | tr -d ' ') dirty path(s)"
  echo "surface digest $(digest)"
  echo "rounds         ${ROUNDS}"
  echo "reps           ${REPS}"
  echo "defeat slots   ${DEFEAT_SLOTS}"
} | tee "${OUT}/provenance_pre.log"

echo "--- regenerating arms from the working tree ---"
"${PY}" research/maple-alphonse-r107b-prefetch-adjudication.py | tee "${OUT}/variants.log"

echo "--- building probe ---"
xcrun swiftc -O research/fern_r99_qmv_probe.swift -o "${PROBE}" || exit 1

# Fault control first: if a deliberately wrong kernel does NOT trip the probe's
# bitwise output gate, every later "diff 0" line is meaningless and the run is
# void.  Cheap settings -- this invocation exists for the gate, not for timing.
echo "--- fault control (expect the bitwise gate to FAIL) ---"
FERN_ROUNDS=1 FERN_REPS=10 FERN_LADDER=2048 FERN_DEFEAT_SLOTS=1 \
  "${PROBE}" "${OUT}/depth1_shipped.metal" "${OUT}/fault_control.metal" \
  >"${OUT}/fault_control.log" 2>&1
if grep -q "VERDICT: all arms bitwise identical" "${OUT}/fault_control.log"; then
  echo "FATAL: fault control was not detected; the output gate is vacuous." | tee -a "${OUT}/fault_control.log"
  exit 2
fi
echo "ok: fault control tripped the bitwise gate"

# Mandatory ordering (the probe enforces it): the identical-source null spread
# is printed before any candidate number.
for mode in resident defeat; do
  if [ "${mode}" = resident ]; then slots=1; else slots="${DEFEAT_SLOTS}"; fi

  echo "--- null control, ${mode} ---"
  FERN_ROUNDS="${ROUNDS}" FERN_REPS="${REPS}" FERN_DEFEAT_SLOTS="${slots}" \
    "${PROBE}" "${OUT}/depth1_shipped.metal" \
    >"${OUT}/null_${mode}.log" 2>&1 || exit 1
  tail -n 12 "${OUT}/null_${mode}.log"

  echo "--- one-axis contrast, ${mode} ---"
  FERN_ROUNDS="${ROUNDS}" FERN_REPS="${REPS}" FERN_DEFEAT_SLOTS="${slots}" \
    "${PROBE}" "${OUT}/depth1_shipped.metal" \
    "${OUT}/noop_control.metal" "${OUT}/depth0_oneaxis.metal" \
    >"${OUT}/oneaxis_${mode}.log" 2>&1 || exit 1
  tail -n 24 "${OUT}/oneaxis_${mode}.log"
done

{
  echo "=== provenance (post-timing) ==="
  echo "utc            $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "surface digest $(digest)"
} | tee "${OUT}/provenance_post.log"

if ! diff -q <(grep 'surface digest' "${OUT}/provenance_pre.log") \
             <(grep 'surface digest' "${OUT}/provenance_post.log") >/dev/null; then
  echo "FATAL: the source tree changed during the run; discard these logs."
  exit 3
fi

# Rule 77: the probe rung must reproduce the shipped dispatch.  Production is
# 2048 threadgroups of 64 threads writing 8*512 bf16 = 8192 B.
if ! grep -q "TG=2048  reference re-run  diff      0 /  65536 bytes   (reference wrote   8192)" \
     "${OUT}/oneaxis_defeat.log"; then
  echo "WARNING: the TG=2048 rung did not write the production 8192 B; check geometry."
fi

echo "--- analysis ---"
"${PY}" research/maple-alphonse-r107b-prefetch-adjudication-analyze.py \
  "${OUT}/null_resident.log" "${OUT}/oneaxis_resident.log" \
  "${OUT}/null_defeat.log" "${OUT}/oneaxis_defeat.log" \
  | tee "${OUT}/verdict.log"
