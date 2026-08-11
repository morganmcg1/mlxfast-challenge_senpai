#!/usr/bin/env bash
# R117-C Stage 1 pre-flight.
#
# Purpose: prove every geometry arm still produces the golden output BEFORE
# spending an hour of GPU on the ladder. The o_proj geometry knob only decides
# which simdgroup owns which output row -- the per-row accumulation order over k
# and j is untouched -- so every setting must be bit-identical to the shipped
# default. If one is not, my source-level bit-exactness argument is wrong and the
# ladder is worthless; better to learn that in 10 minutes than in 70.
#
# Rule 33 (MLX caches compiled pipelines by function name) is handled at the
# source level instead: `lagunaOProjRowsPerSimdgroupSuffix` is appended to all
# four o_proj kernel-name literals and is distinct for every (rps, ns) pair, so
# no two arms can share a pipeline. benchmark.sh does not echo kernel names
# (the ruler campaign's `kernels` column read "none" for all 35 runs), so there
# is nothing to scrape from the log.
set -u
cd "$(dirname "$0")/../.." || exit 2
OUT=/tmp/r117-stage1-preflight.tsv
printf 'arm\trc\tpassed\tdecode_s_per_token\tgolden\n' > "$OUT"

run() {
  local label="$1"; shift
  rm -f score.json score.local-iterate.json
  if [ "$#" -gt 0 ]; then
    env "$@" ./benchmark.sh --local-submit > "/tmp/preflight-${label}.log" 2>&1
  else
    ./benchmark.sh --local-submit > "/tmp/preflight-${label}.log" 2>&1
  fi
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null
  if [ ! -f score.json ]; then
    printf '%s\t%d\tNO_SCORE\tNA\tNA\n' "$label" "$rc" | tee -a "$OUT"
    return
  fi
  local dec pas gld
  dec=$(jq -r '.metrics.decode_seconds_per_token // "NA"' score.json)
  pas=$(jq -r 'if .metrics.passed_correctness == null then "NA" else (.metrics.passed_correctness|tostring) end' score.json)
  gld=$(jq -r '(.metrics.golden_hash // .golden_hash // "NA")|tostring' score.json)
  printf '%s\t%d\t%s\t%s\t%s\n' "$label" "$rc" "$pas" "$dec" "$gld" | tee -a "$OUT"
  cp score.json "/tmp/preflight-${label}.score.json"
}

run C
run R1 DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=1
run R8 DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=8
run N4 DARKBLOOM_OPROJ_SIMDGROUPS=4
rm -f score.json score.local-iterate.json
echo "--- ${OUT} ---"
cat "$OUT"
