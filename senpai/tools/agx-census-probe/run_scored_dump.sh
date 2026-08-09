#!/usr/bin/env bash
# Capture MLX's verbose MSL dump from the *scored* runtime path.
#
# Why this vehicle and not `correctness` / `correctness-trace`:
# runtimeWorkerOptions (Sources/MLXFastCLI/main.swift:1239) defaults
# `forwardsWorkerStderr: false`, and the only call site that passes `true` is
# the local-iterate/local-submit benchmark (main.swift:315-318). Every other
# subcommand drops the worker's stderr, so a dump emitted inside the worker is
# unrecoverable there. The worker also nulls STDOUT_FILENO
# (RuntimeWorkerProtocolIO.isolatingStandardIO, LagunaRuntimeWorker.swift:1187)
# and runs under a `(deny file-write*)` sandbox
# (writeRuntimeWorkerSandboxProfile, main.swift:1612), so neither the original
# fd 1 nor a fresh open() works; the runtime aims fd 1 at the stderr pipe.
#
# Usage: bash senpai/tools/agx-census-probe/run_scored_dump.sh OUT_LOG
set -uo pipefail
OUT="${1:?usage: run_scored_dump.sh OUT_LOG}"
mkdir -p "$(dirname "$OUT")"
export DARKBLOOM_R92_DUMP_TO_STDERR=1
export DARKBLOOM_R92_DUMP_LIMIT="${DARKBLOOM_R92_DUMP_LIMIT:-2000}"
./benchmark.sh --local-iterate >"$OUT" 2>&1
rc=$?
echo "run_scored_dump exit=${rc} bytes=$(wc -c <"$OUT")" >&2
echo "worker_lines=$(grep -c '^mlxfast-worker: ' "$OUT")" >&2
echo "emissions=$(grep -c 'Generated source code for ' "$OUT")" >&2
exit "$rc"
