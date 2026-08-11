#!/usr/bin/env bash
# Research-only (PR #714, R119-C): correctness gate for the three shared-expert
# SwiGLU QMV threadgroup-width arms.
#
# Two legs per arm:
#   1. teacher-forced + free-run decode through the already-built worker, which
#      catches a wrong row mapping immediately and cheaply;
#   2. the vendored-upstream oracle, which is zero-tolerance
#      (maximumAbsoluteLogitError == 0) and therefore the bit-identity gate the
#      assignment asks for.
#
#   OUT=/tmp/r119c-correct bash research/maple_r119c_correctness.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-research/r119c-runs/correctness}"
STEPS="${STEPS:-64}"
mkdir -p "${OUT}"

echo "### HEAD: $(git rev-parse HEAD)"
echo "### worker: $(ls -l .build-worker/release/mlxfast-runtime-worker | awk '{print $6,$7,$8}')"

for tg in 64 128 256; do
  echo "=== decode arm TG=${tg} t=$(date -u +%H:%M:%S)"
  DARKBLOOM_SHARED_QMV_TG="${tg}" \
    python3 research/decode_probe.py --steps "${STEPS}" --free-run \
      --free-run-bootstrap 1041 \
      --stderr "${OUT}/tg${tg}.err" \
      --dump-tokens "${OUT}/tg${tg}.tokens" \
      >"${OUT}/tg${tg}.log" 2>&1
  echo "--- rc=$?"
  grep -E "free-run tokens:|teacher-forced|worker error|Fatal|error:" \
    "${OUT}/tg${tg}.log" | head -5
done

echo "=== free-run token identity across arms"
for tg in 128 256; do
  if cmp -s "${OUT}/tg64.tokens" "${OUT}/tg${tg}.tokens"; then
    echo "TOKENS_IDENTICAL tg${tg}_vs_tg64=yes"
  else
    echo "TOKENS_IDENTICAL tg${tg}_vs_tg64=NO"
  fi
done

for tg in 64 128 256; do
  echo "=== upstream equivalence arm TG=${tg} t=$(date -u +%H:%M:%S)"
  DARKBLOOM_SHARED_QMV_TG="${tg}" \
    bash research/run_upstream_equivalence.sh >"${OUT}/equiv-tg${tg}.log" 2>&1
  echo "--- rc=$?"
  grep -E "EQUIVALENCE_EXACT_STEPS=|EQUIVALENCE_EXIT=|Test run with|error:" \
    "${OUT}/equiv-tg${tg}.log" | tail -6
  git checkout -- Package.resolved 2>/dev/null || true
done
echo "=== done t=$(date -u +%H:%M:%S)"
