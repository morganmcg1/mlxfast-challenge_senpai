#!/usr/bin/env bash
# Research-only verification wrapper for the 50 MiB command-buffer byte cap.
#
# Both --local-iterate arms run from the same commit and the same binary. The
# control arm restores the previous shipped value through the environment,
# which the in-tree setenv(..., overwrite: 0) deliberately allows. This host is
# a 48 GiB M4 Pro, so DARKBLOOM_STARTUP_MEMORY_PROFILE=full is required or the
# edited block never executes.
set -uo pipefail

cd "$(dirname "$0")/.."

export DARKBLOOM_STARTUP_MEMORY_PROFILE=full

summarize() {
    jq -M -c --arg arm "$1" '{
        arm: $arm,
        commit: .metrics.commit,
        max_abs_diff: .metrics.max_abs_diff,
        passed_correctness: .metrics.passed_correctness,
        checked_steps: .metrics.checked_steps,
        golden_hash: .metrics.golden_hash,
        prefill_s_per_tok: .metrics.prefill_seconds_per_token,
        decode_s_per_tok: .metrics.decode_seconds_per_token,
        peak_ram_gb: .metrics.peak_ram_gb
    }' "score.local-iterate.$1.json"
}

run_arm() {
    local label="$1"
    shift
    echo "=== ARM ${label} (extra env: $*) ==="
    env "$@" research/run_local_benchmark.sh --local-iterate
    local status=$?
    echo "=== ARM ${label} exit=${status} ==="
    cp score.local-iterate.json "score.local-iterate.${label}.json"
    summarize "${label}"
}

run_arm candidate
run_arm baseline MLX_MAX_MB_PER_BUFFER=200 MLX_MAX_OPS_PER_BUFFER=400

echo "=== PAIR SUMMARY ==="
summarize candidate
summarize baseline

echo "=== swift test (stock profile) ==="
env -u DARKBLOOM_STARTUP_MEMORY_PROFILE swift test --force-resolved-versions 2>&1 \
    | tail -60
test_status="${PIPESTATUS[0]}"
git checkout -- Package.resolved
echo "=== swift test exit=${test_status} ==="
