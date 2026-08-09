#!/usr/bin/env bash
# Recover an MLX verbose MSL dump from a runtime-worker run.
#
# The worker sandbox is `(deny file-write*)` except /dev/null, so the dump is
# routed to the already-open stderr pipe (dup2(STDERR_FILENO, STDOUT_FILENO)).
# The parent drains that pipe and forwards every line with the fixed prefix
# `mlxfast-worker: ` (LagunaRuntimeWorker.swift:1284), after per-line redaction
# that collapses any line containing "expected"/"actual" to
# "token-validation-failed" (redactedWorkerStderrLine, :1392). Report the count
# of collapsed lines so a corrupted translation unit cannot pass silently.
#
# Usage: bash strip_worker_prefix.sh IN_LOG OUT_LOG
set -uo pipefail
IN="${1:?usage: strip_worker_prefix.sh IN_LOG OUT_LOG}"
OUT="${2:?usage: strip_worker_prefix.sh IN_LOG OUT_LOG}"

grep '^mlxfast-worker: ' "$IN" | sed 's/^mlxfast-worker: //' >"$OUT"
echo "in_lines=$(wc -l <"$IN") out_lines=$(wc -l <"$OUT")" >&2
echo "redacted_lines=$(grep -c '^token-validation-failed$' "$OUT")" >&2
echo "emissions=$(grep -c '^Generated source code for ' "$OUT")" >&2
