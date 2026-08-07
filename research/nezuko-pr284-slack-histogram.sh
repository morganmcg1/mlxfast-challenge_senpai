#!/usr/bin/env bash
# PR284 step 1: capture the lm-head certificate-slack histogram over one real
# decode run, then restore the tree.
#
# Emits one `SLACKHIST c1 c2 c3 c5 c7 c9 c13 c17 c25 c33` line per decode step,
# where cT = #{ rows with (thr - coarse)/delta <= T }. cT is a conservative
# upper bound on the survivor count a coarser bit-plane tier must refine:
# T=1 is today's 4-bit screen, T=5 a 3-bit tier, T=9 a 2-bit tier, T=17 a
# 1-bit tier.
#
# The probe lives in research/nezuko-pr284-slack-probe.patch and is reverted on
# exit, so no instrument is ever committed under Sources/.
set -uo pipefail
cd "$(dirname "$0")/.."

PATCH=research/nezuko-pr284-slack-probe.patch
OUT=research/artifacts/nezuko-pr284-slack-hist.txt
ERR=/tmp/nezuko-pr284-slack.worker.err
STEPS="${1:-128}"

cleanup() {
  git apply -R "$PATCH" 2>/dev/null
  git checkout -- Package.resolved 2>/dev/null
}
trap cleanup EXIT

git apply "$PATCH" || { echo "FATAL: probe patch did not apply"; exit 1; }
mkdir -p .build-worker/clang-module-cache research/artifacts

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
  || { echo "FATAL: worker build failed"; exit 1; }

DARKBLOOM_LMHEAD_SLACK_PROBE=1 \
  python3 research/decode_probe.py --steps "$STEPS" --stderr "$ERR" \
  || { echo "FATAL: decode probe failed; see $ERR"; tail -n 20 "$ERR"; exit 1; }

grep '^SLACKHIST' "$ERR" > "$OUT"
echo "captured $(wc -l < "$OUT") SLACKHIST lines for $STEPS decode steps -> $OUT"
head -n 3 "$OUT"
