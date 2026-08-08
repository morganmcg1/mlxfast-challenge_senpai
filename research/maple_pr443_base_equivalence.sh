#!/usr/bin/env bash
# Research-only (PR #443): does the *unchanged base* fail the equivalence
# oracle the same way this branch does?
#
# On this M4 Pro host the oracle fails with prefill
# `maximumAbsoluteLogitError: 0.125` (one bf16 ULP) while every decode step is
# exactly 0 and every argmax matches. AGENTS.md: "If a non-M5 host disagrees
# with a public golden, test the unchanged base." This branch touches exactly
# two files, so restoring both to BASE_SHA reproduces the base bit-for-bit
# without a fresh worktree or a full Cmlx rebuild.
#
# A matching base failure means the divergence is a host/near-tie artefact and
# not attributable to DARKBLOOM_SHARED_SCALE_HALVED (which is default-OFF and
# decode-only, so it cannot reach prefill at all). A base PASS would mean this
# branch broke something and must not be timed.
#
#   BASE_SHA=730e9c2... bash research/maple_pr443_base_equivalence.sh
set -uo pipefail

BASE_SHA="${BASE_SHA:-730e9c2be89a4ed8cf860e52f930f7ff222d4c95}"
OUT="${OUT:-/tmp/maple-pr443-base-equiv}"
FILES=(Sources/MLXFastModel/LagunaRuntimeModel.swift
       Sources/MLXFastModel/LagunaRuntimeWeights.swift)
mkdir -p "${OUT}"

if ! git diff --quiet -- "${FILES[@]}"; then
  echo "refusing: patched sources are dirty; commit or stash first" >&2
  exit 2
fi

restore() {
  echo "### restoring branch sources"
  git checkout HEAD -- "${FILES[@]}"
  git checkout -- Package.resolved 2>/dev/null || true
}
trap restore EXIT

echo "### checking out ${BASE_SHA} versions of the two edited files"
git checkout "${BASE_SHA}" -- "${FILES[@]}" || exit 3
git --no-pager diff --stat HEAD -- "${FILES[@]}" | tee "${OUT}/reverted.txt"

bash research/run_upstream_equivalence.sh >"${OUT}/base-equivalence.log" 2>&1
echo "base equivalence rc=$?" | tee "${OUT}/summary.txt"
grep -E 'EQUIVALENCE_EXACT_STEPS|EQUIVALENCE_EXIT|Executed [0-9]+ test' \
  "${OUT}/base-equivalence.log" | tee -a "${OUT}/summary.txt"
grep -o '"label" : "[a-z0-9-]*",$' -A0 "${OUT}/base-equivalence.log" >/dev/null 2>&1
python3 - "${OUT}/base-equivalence.log" <<'PY' | tee -a "${OUT}/summary.txt"
import json, re, sys
text = open(sys.argv[1], errors="replace").read()
start = text.find('{\n  "decodeTokenCount"')
if start < 0:
    start = text.find('{\n  "promptTokenCount"')
if start < 0:
    print("no equivalence report found")
    raise SystemExit(0)
depth = 0
for i in range(start, len(text)):
    if text[i] == '{':
        depth += 1
    elif text[i] == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break
report = json.loads(text[start:end])
for step in report["steps"]:
    print("base %-10s maxAbsLogitErr=%-8s argmax %s vs %s %s" % (
        step["label"], step["maximumAbsoluteLogitError"],
        step["runtimeToken"], step["upstreamToken"],
        "MATCH" if step["runtimeToken"] == step["upstreamToken"] else "DIFFER"))
PY
