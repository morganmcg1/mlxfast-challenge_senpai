#!/bin/bash
# r99-A: attribute an upstream-equivalence outcome to a specific kernel change.
#
# The gate failed on the shipped candidate with a prefill-only max-abs logit
# error of 0.125 while all eight decode steps were bit-exact. AGENTS.md requires
# testing the unchanged base before reading that as candidate-induced drift, so
# this driver swaps each variant into the scored source in turn and runs the
# same oracle. The worktree is restored from HEAD on every exit path.
set -u

cd "$(dirname "$0")/.." || exit 1

TARGET="Sources/MLXFastModel/LagunaRuntimeModel.swift"
VARIANTS="${*:-v_base v_d4 v_epi v_d4epi}"

restore() { git checkout HEAD -- "${TARGET}"; }
trap restore EXIT INT TERM

for v in ${VARIANTS}; do
    src="/tmp/${v}.swift"
    if [ ! -f "${src}" ]; then
        echo "EQUIV_VARIANT=${v} MISSING_SOURCE=${src}"
        continue
    fi
    cp "${src}" "${TARGET}"
    echo "===== EQUIV_VARIANT=${v} bytes=$(wc -c < "${TARGET}" | tr -d ' ') ====="
    out="$(research/run_upstream_equivalence.sh 2>&1)"
    status=$?
    printf '%s\n' "${out}"
    maxima="$(printf '%s\n' "${out}" | grep '"maximumAbsoluteLogitError"' \
        | sed 's/.*: //; s/,$//' | tr '\n' ' ')"
    echo "EQUIV_SUMMARY variant=${v} status=${status} max_abs_per_case=[ ${maxima}]"
done

restore
trap - EXIT INT TERM
echo "EQUIV_CONTROL_DONE restored=$(wc -c < "${TARGET}" | tr -d ' ')"
