#!/usr/bin/env bash
# R125-A correctness certificate for the DARKBLOOM_SHARED_QMV_TG selector.
#
# Runs, with a hook-free worker built from HEAD:
#   1. teacher-forced 200-step golden decode at TG=64 and TG=256;
#   2. 64-step self-fed free run at both widths, compared by sequence hash;
#   3. the vendored-Laguna upstream-equivalence oracle at both widths.
#
# Research-only.  Never sets MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT.
#
#   OUT=/tmp/maple-r125a-correct bash research/maple_r125a_correctness.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/maple-r125a-correct}"
FREE_STEPS="${FREE_STEPS:-64}"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty (is the gpuprof hook still applied?)" >&2
  exit 2
fi
echo "### HEAD: $(git rev-parse HEAD)"

echo "### building hook-free worker"
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
[ "${rc}" -eq 0 ] || exit 3

for tg in 64 256; do
  echo "########## teacher-forced golden, TG=${tg} ##########"
  DARKBLOOM_SHARED_QMV_TG="${tg}" python3 research/decode_probe.py \
    --steps 200 --prefill --stderr "${OUT}/tf_tg${tg}.err" \
    --dump-tokens "${OUT}/tf_tg${tg}.tokens" 2>&1 \
    | tee "${OUT}/tf_tg${tg}.log" | grep -E "teacher-forced|prefill|decode steps"

  echo "########## free run ${FREE_STEPS} steps, TG=${tg} ##########"
  DARKBLOOM_SHARED_QMV_TG="${tg}" python3 research/decode_probe.py \
    --steps "${FREE_STEPS}" --free-run --stderr "${OUT}/fr_tg${tg}.err" \
    --dump-tokens "${OUT}/fr_tg${tg}.tokens" 2>&1 \
    | tee "${OUT}/fr_tg${tg}.log" | grep -E "free-run"
done

echo "########## token identity ##########"
for pair in tf fr; do
  if cmp -s "${OUT}/${pair}_tg64.tokens" "${OUT}/${pair}_tg256.tokens"; then
    echo "${pair}: TG64 == TG256 TOKENS_IDENTICAL"
  else
    echo "${pair}: TOKENS_DIFFER"
  fi
done

for tg in 64 256; do
  echo "########## upstream equivalence oracle, TG=${tg} ##########"
  DARKBLOOM_SHARED_QMV_TG="${tg}" bash research/run_upstream_equivalence.sh \
    >"${OUT}/eq_tg${tg}.log" 2>&1
  echo "eq TG=${tg} wrapper_exit=$?"
  grep -E "EQUIVALENCE_EXACT_STEPS|EQUIVALENCE_EXIT" "${OUT}/eq_tg${tg}.log"
  grep -o '"maximumAbsoluteLogitError" : [0-9.]*' "${OUT}/eq_tg${tg}.log" \
    | sort | uniq -c
done
git checkout -- Package.resolved 2>/dev/null || true
