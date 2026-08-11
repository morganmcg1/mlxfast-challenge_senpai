#!/bin/bash
# Smoke test: does every tool the handoff documents cite still RUN on this branch?
# Read-only. It first re-checks, every run, that no tool can invoke the submission
# CLI, then prints one line per tool: OK / USAGE / ARGS / FAIL + first error.
cd "$(dirname "$0")/../.." || exit 2

# --- channel-safety invariant -------------------------------------------------
# Every tool here is an analysis tool. None may INVOKE the submission CLI: running
# the smoke test must never be able to spend a draw. "I grepped once and remember
# it was fine" is not a property; this is. Comments/docstrings that merely NAME
# `mlxfast submissions` as the provenance of captured data are allowed -- what is
# banned is execution (subprocess/os.system/os.popen/$( ), or a bare shell command).
# NB: an earlier version of this check also flagged a literal backtick before
# `mlxfast`, which made every docstring that CITES the CLI as its data provenance
# fail the scan -- a check that cries wolf on prose gets deleted, so it matches
# execution syntax only. This script excludes itself, since it names the patterns.
unsafe=$(grep -rnE "subprocess[^)]*mlxfast|os\.(system|popen)\([^)]*mlxfast|\\\$\(mlxfast|^[[:space:]]*mlxfast[[:space:]]" \
           --exclude=run_all_tools_smoke.sh research/tools/ 2>/dev/null)
if [ -n "$unsafe" ]; then
  echo "CHANNEL-SAFETY FAILURE: a tool can invoke the submission CLI:"
  echo "$unsafe" | cut -c1-200
  exit 3
fi
echo "SAFE  no tool invokes the submission CLI (execution-pattern scan clean)"
# ------------------------------------------------------------------------------
# These three are filters, not reports: they take arguments and are expected to
# exit nonzero with no argv. Verified 16:27Z: extract_results.py <pr_number> [limit],
# extract_submission_corpus.py <src> <dst>, sigma_pseudoreplicate_probe.py <path>.
# Two acceptable no-arg behaviours: a clean usage message (preferred), or a bare
# IndexError from argv indexing (tolerated on the older tools).
NEEDS_ARGS="extract_results.py extract_submission_corpus.py sigma_pseudoreplicate_probe.py"

for f in research/tools/*.py; do
  base=$(basename "$f")
  case " $NEEDS_ARGS " in
    *" $base "*)
      out=$(python3 "$f" 2>&1)
      rc=$?
      if [ $rc -ne 0 ] && echo "$out" | grep -qi "^Usage:"; then
        echo "USAGE $f (filter: needs argv, prints usage and exits $rc)"
      elif echo "$out" | grep -q "IndexError: list index out of range"; then
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
