#!/usr/bin/env bash
# BASE_SHA attribution control for the upstream-equivalence prefill delta seen
# on this non-M5 M4 Pro host.
#
#   bash research/nezuko_q12_equiv_base_control.sh <BASE_SHA> <OUTDIR>
#
# research/run_upstream_equivalence.sh prescribes: "on a non-M5 host, compare
# the unchanged BASE_SHA before attributing drift." The Q12 submission surface
# is exactly one file, so the control is to restore that one file to its
# BASE_SHA content, rerun the oracle, and compare the per-step report. If the
# unchanged base shows the same prefill error, the divergence is a property of
# the host, not of the candidate.
#
# The revert is undone by an EXIT trap and verified against HEAD afterwards, so
# an interrupted run cannot leave a mutated submission surface behind.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE_SHA="${1:?BASE_SHA}"
OUTDIR="${2:?outdir}"
TARGET="Sources/MLXFastModel/LagunaRuntimeModel.swift"
mkdir -p "$OUTDIR"

head_digest="$(git rev-parse "HEAD:${TARGET}")"
restore() {
  git checkout HEAD -- "$TARGET"
  git checkout -- Package.resolved 2>/dev/null || true
  now="$(git hash-object "$TARGET")"
  if [[ "$now" == "$head_digest" ]]; then
    echo "restore: ${TARGET} matches HEAD (${head_digest})"
  else
    echo "restore: FAILED, ${TARGET} is ${now} not ${head_digest}" >&2
  fi
}
trap restore EXIT

echo "=== $(date -u +%H:%M:%S) candidate blob ${head_digest}"
echo "=== $(date -u +%H:%M:%S) reverting ${TARGET} to ${BASE_SHA}"
git show "${BASE_SHA}:${TARGET}" > "$TARGET" || exit 2
echo "=== base blob $(git hash-object "$TARGET") ($(wc -c < "$TARGET") bytes)"
git --no-pager diff --stat -- "$TARGET"

echo "=== $(date -u +%H:%M:%S) upstream equivalence oracle on unchanged base"
bash research/run_upstream_equivalence.sh > "${OUTDIR}/equivalence_base.log" 2>&1
eq=$?
grep -E '"label"|AbsoluteLogitError|Token" :|^EQUIVALENCE_' "${OUTDIR}/equivalence_base.log" \
  | sed 's/^/base /'
echo "BASE_EQUIVALENCE_EXIT=${eq}"
echo "=== $(date -u +%H:%M:%S) base control done"
