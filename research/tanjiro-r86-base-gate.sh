#!/usr/bin/env bash
# R86-A rev2 base gate: matched-pair timing of the adopted organizer frontier
# base (HEAD, 7687c2e4 content) against the base it replaced (f64456dd), then
# the upstream-equivalence oracle on the adopted content.
#
# Only the 8 editable paths that the adoption changed are flipped, so the two
# arms differ by exactly the adoption and nothing else.
set -uo pipefail
cd "$(dirname "$0")/.."

OLD_REF="f64456dd2dc503af080dca65bddfb922164c7bc5"
OUT="research/r86-gate-results"
mkdir -p "$OUT"

PATHS=(
  "Sources/MLXFastModel/LagunaLmHeadPrune.swift"
  "Sources/MLXFastModel/LagunaRuntimeModel.swift"
  "Sources/MLXFastModel/LagunaRuntimeWeights.swift"
  "Vendor/mlx-swift-lm/Libraries/MLXLMCommon/RoPEApplication.swift"
  "Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp"
  "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h"
  "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp"
  "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp"
)

export MLXFAST_LOCAL_FAN_PROMPT=0
# MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT is deliberately left unset.

run_arm() {
  local arm="$1" rep="$2" ref
  if [ "$arm" = "new" ]; then ref="HEAD"; else ref="$OLD_REF"; fi
  git checkout "$ref" -- "${PATHS[@]}"
  echo "=== rep ${rep} arm ${arm} ref ${ref} start $(date -u +%FT%TZ) surface=$(cat "${PATHS[@]}" | shasum -a 256 | cut -c1-12) ==="
  MLXFAST_SCORE_PATH=score.json ./benchmark.sh --local-iterate \
    > "${OUT}/${arm}-r${rep}.log" 2>&1
  echo "=== rep ${rep} arm ${arm} exit $? $(date -u +%FT%TZ) ==="
  if [ -f score.json ]; then
    cp score.json "${OUT}/${arm}-r${rep}.json"
    python3 -c "import json,sys;d=json.load(open('score.json'));m=d.get('metrics',{});print({'passed':d.get('passed'),'score':d.get('score'),'correct':m.get('passed_correctness'),'steps':m.get('checked_steps'),'golden':str(m.get('golden_hash'))[:12],'decode_s':m.get('decode_seconds_per_token'),'prefill_s':m.get('prefill_seconds_per_token')})" || true
  fi
}

correct_of() {
  python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('metrics',{}).get('passed_correctness'))" "$1" 2>/dev/null
}

# Rep 1 first, then gate on correctness of the adopted base before spending the
# rest of the block. If the adopted base fails the tripwire we still measure the
# old base once, because a near-tie argmax divergence on this non-M5 host is
# only interpretable against the unchanged predecessor.
run_arm new 1
run_arm old 1

if [ "$(correct_of "${OUT}/new-r1.json")" != "True" ]; then
  echo "=== ABORT: adopted base failed the 64-step tripwire; old-base control captured ==="
  git checkout HEAD -- "${PATHS[@]}"
  git reset -q HEAD -- "${PATHS[@]}"
  exit 10
fi

for rep in 2 3; do
  if [ $((rep % 2)) -eq 0 ]; then order="old new"; else order="new old"; fi
  for arm in $order; do run_arm "$arm" "$rep"; done
done

git checkout HEAD -- "${PATHS[@]}"
git reset -q HEAD -- "${PATHS[@]}"

echo "=== equivalence oracle on adopted content $(date -u +%FT%TZ) ==="
research/run_upstream_equivalence.sh > "${OUT}/equivalence.log" 2>&1
echo "=== equivalence exit $? ==="
tail -5 "${OUT}/equivalence.log"

echo "=== done $(date -u +%FT%TZ) ==="
