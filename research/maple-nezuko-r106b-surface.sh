#!/usr/bin/env bash
# R106-B: Rule 75 surface accounting for the edited source, computed at whatever
# commit is checked out.  Prints the numbers section E of the report quotes, so
# that section is reproducible rather than transcribed.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE="${BASE:-446fe9875d1f95b1216628b5809a99da844e5c79}"
F=Sources/MLXFastModel/LagunaRuntimeModel.swift

echo "commit: $(git rev-parse HEAD)"
echo "base:   ${BASE}"
echo
echo "--- ${F} at base ${BASE:0:8} ---"
git show "${BASE}:${F}" | shasum -a 256 | sed 's/-$/(base)/'
printf 'bytes: %s\n' "$(git show "${BASE}:${F}" | wc -c | tr -d ' ')"
echo
echo "--- ${F} at HEAD ---"
shasum -a 256 "${F}"
printf 'bytes: %s\n' "$(wc -c < "${F}" | tr -d ' ')"
echo
echo "--- diff vs base ---"
git diff --shortstat "${BASE}" -- "${F}"
git diff --stat "${BASE}" -- Sources/
echo
echo "--- editable-surface budget (senpai/check-editable-budget.sh) ---"
senpai/check-editable-budget.sh "${BASE}" 2>&1 | tail -5
