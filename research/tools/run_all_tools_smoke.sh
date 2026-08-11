#!/bin/bash
# Smoke test: does every tool the handoff documents cite still RUN on this branch?
# Read-only. None of these tools touch the submission channel (verified by grep for
# `mlxfast` before this was written). Prints one line per tool: OK / FAIL + first error.
cd "$(dirname "$0")/../.." || exit 2
# These three are filters, not reports: they take arguments and are expected to
# exit nonzero with no argv. Verified 16:23Z: extract_results.py <substr> [limit],
# extract_submission_corpus.py <src> <dst>, sigma_pseudoreplicate_probe.py <path>.
NEEDS_ARGS="extract_results.py extract_submission_corpus.py sigma_pseudoreplicate_probe.py"

for f in research/tools/*.py; do
  base=$(basename "$f")
  case " $NEEDS_ARGS " in
    *" $base "*)
      out=$(python3 "$f" 2>&1)
      if echo "$out" | grep -q "IndexError: list index out of range"; then
        echo "ARGS  $f (filter: needs argv, no-arg run fails as designed)"
      else
        echo "FAIL  $f :: unexpected no-arg behaviour :: $(echo "$out" | tail -1 | cut -c1-160)"
      fi
      continue;;
  esac
  out=$(python3 "$f" 2>&1)
  rc=$?
  if [ $rc -eq 0 ]; then
    echo "OK    $f"
  else
    echo "FAIL($rc) $f :: $(echo "$out" | tail -2 | tr '\n' ' ' | cut -c1-200)"
  fi
done
