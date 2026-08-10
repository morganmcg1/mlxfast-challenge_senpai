#!/bin/bash
# Research-only (PR #597, R106-J Deliverable B2): interleaved per-KERNEL A/B for
# `DARKBLOOM_QMV_WIDE_CODES` on `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1`.
#
# Why per-kernel and not `./benchmark.sh --local-iterate`: Rule 86 says a
# local-iterate delta is never evidence for or against a lever (identical code
# produced a +0.9 % "score" delta; two relaunches differ by 1.3 %). The unit the
# assignment asks me to convert from is us/step, so the instrument has to be the
# GPU timestamp of the dispatch itself, which is host-independent and has fixed
# geometry at decode.
#
# One worker PROCESS per arm, ABBA inside every rep, so process-level drift
# cannot line up with the arm labels. `DARKBLOOM_GPU_PROFILE_SPLIT=1` puts one
# dispatch per command buffer, which is what makes a sub-us per-call effect
# visible at all.
#
#   REPS=3 STEPS=33 OUT=/tmp/r106j-abba \
#     bash research/maple_frieren_r106j_wide_codes_abba.sh
#
# Applies research/nezuko-pr158-gpuprof-hook.patch, builds, runs, and RESTORES
# Sources/ at the end. The instrumented worker never gets committed.
set -u
cd "$(dirname "$0")/.."

STEPS=${STEPS:-33}
REPS=${REPS:-3}
OUT=${OUT:-/tmp/r106j-abba}
ORDER=${ORDER:-"off on on off"}
PATCH=research/nezuko-pr158-gpuprof-hook.patch
mkdir -p "$OUT"

cleanup() {
  echo "=== restoring Sources/ ==="
  git checkout -- Sources/ 2>/dev/null || true
  git checkout -- Package.resolved 2>/dev/null || true
  git status --short
}
trap cleanup EXIT

echo "=== applying $PATCH ==="
git apply "$PATCH" || exit 1
git status --short

echo "=== building instrumented worker ==="
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-${PWD}/.build-worker/clang-module-cache}" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker || exit 1

echo "=== ABBA: order '$ORDER' x $REPS reps, $STEPS steps ==="
idx=0
for rep in $(seq 1 "$REPS"); do
  for arm in $ORDER; do
    idx=$((idx + 1))
    tag=$(printf "%02d-rep%s-%s" "$idx" "$rep" "$arm")
    unset DARKBLOOM_QMV_WIDE_CODES
    case "$arm" in
      on) export DARKBLOOM_QMV_WIDE_CODES=1 ;;
    esac
    echo "=== $tag ==="
    DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
      python3 research/decode_probe.py --steps "$STEPS" --profile \
        --profile-top 8 --stderr "$OUT/$tag.err" \
        >"$OUT/$tag.log" 2>&1
    status=$?
    grep -E "teacher-forced|per steady step|swiglu_qmv_rows1" "$OUT/$tag.log" | head -4
    echo "exit=$status"
    [ "$status" -eq 0 ] || exit "$status"
  done
done
echo "logs in $OUT"
