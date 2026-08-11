#!/usr/bin/env bash
# R119-B smoke: does the grid-appended shared+routed QMV kernel compile, get
# selected on the scored decode path, and produce byte-identical tokens?
# Research-only; not on editablePaths.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
OUT="${OUT:-/tmp/edward-r119b-smoke}"
STEPS="${STEPS:-40}"
mkdir -p "${OUT}"

run_arm() {
  local tag="$1" gate="$2"
  DARKBLOOM_SHARED_ROUTED_QMV_FUSED="${gate}" DARKBLOOM_TRACE_FUSION=1 \
    python3 research/decode_probe.py --steps "${STEPS}" --prefill \
      --stderr "${OUT}/${tag}.err" \
      --dump-steps "${OUT}/${tag}.steps" \
      --dump-tokens "${OUT}/${tag}.tokens" \
      >"${OUT}/${tag}.log" 2>&1
  echo "### ${tag} (gate=${gate}) exit=$?"
  grep -E "teacher-forced|prefill 512|decode_begin|steady|median|mean" "${OUT}/${tag}.log" || true
  grep -c "fusion active" "${OUT}/${tag}.err" 2>/dev/null | sed 's/^/fusion-active-lines: /'
  grep -E "shared\+routed gate/up QMV|routed gate/up QMV \+ SwiGLU \(packed, producer keys\)|shared" \
    "${OUT}/${tag}.err" 2>/dev/null | sort -u || true
}

run_arm off 0
run_arm on 1

echo "### token diff (off vs on)"
if cmp -s "${OUT}/off.tokens" "${OUT}/on.tokens"; then
  echo "TOKENS_IDENTICAL"
else
  echo "TOKENS_DIFFER"
  diff "${OUT}/off.tokens" "${OUT}/on.tokens" | head -20
fi
