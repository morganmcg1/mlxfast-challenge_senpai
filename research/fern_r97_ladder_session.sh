#!/usr/bin/env bash
# R97-A Stage 2 rung-ladder session driver (research only, not submitted).
#
# Applies research/fern-r97-rung-ladder.patch, builds the ladder worker,
# restores the pristine source, then runs the nested session with the rung
# control word wired to the same file the probe drives through --glue-map.
#
#   OUT=/tmp/r97/ladder MODE=block bash research/fern_r97_ladder_session.sh
#   OUT=/tmp/r97/perrun MODE=perrun bash research/fern_r97_ladder_session.sh
#
# MODE=block  P=12 R=9 S=248 PLACEBO_EVERY=8 SCHEDULE=rand:0,1,2  (ranking)
# MODE=perrun P=8  R=8 S=248 PLACEBO_EVERY=0 SCHEDULE=perrun:0,1,2 (absolute)
set -uo pipefail
cd "$(dirname "$0")/.."

OUT="${OUT:?set OUT}"
MODE="${MODE:-block}"
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
PATCH=research/fern-r97-rung-ladder.patch
SKIP_BUILD="${SKIP_BUILD:-0}"

if [ "$MODE" = "block" ]; then
  P="${P:-12}"; R="${R:-9}"; S="${S:-248}"
  SCHEDULE="${SCHEDULE:-rand:0,1,2}"; PLACEBO_EVERY="${PLACEBO_EVERY:-8}"
else
  P="${P:-8}"; R="${R:-8}"; S="${S:-248}"
  SCHEDULE="${SCHEDULE:-perrun:0,1,2}"; PLACEBO_EVERY="${PLACEBO_EVERY:-0}"
fi

if [ "$SKIP_BUILD" != "1" ]; then
  git apply "$PATCH" || { echo "patch did not apply"; exit 1; }
  mkdir -p .build/clang-module-cache .build-worker/clang-module-cache
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  rc=$?
  git checkout HEAD -- "$SRC"
  git checkout -- Package.resolved 2>/dev/null || true
  [ "$rc" -eq 0 ] || { echo "ladder build failed rc=$rc"; exit 1; }
  echo "ladder worker built; worktree restored:"
  git status --porcelain
fi

mkdir -p "$OUT"
export DARKBLOOM_R97_RUNG_MAP="$(cd "$OUT" && pwd)/glue.bin"
echo "rung map -> $DARKBLOOM_R97_RUNG_MAP"

OUT="$OUT" P="$P" R="$R" S="$S" SCHEDULE="$SCHEDULE" \
  PLACEBO_EVERY="$PLACEBO_EVERY" WARMUP_RUNS="${WARMUP_RUNS:-1}" \
  GATE_C="${GATE_C:-40}" SEED="${SEED:-97}" \
  bash research/fern_r93_nested_session.sh
