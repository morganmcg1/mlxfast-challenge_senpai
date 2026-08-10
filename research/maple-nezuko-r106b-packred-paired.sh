#!/usr/bin/env bash
# R106-B Stage B — EVIDENCE campaign for the PACKRED packed-cross-lane-reduction sliding decode
# attention kernel, exactly as preregistered in
# research/maple-nezuko-r106b-stageb-amendment1.md (section 4.4).
#
# Design (Amendment 2): one binary, gate-selected, control-anchored blocks of
# four runs in one session. Each block is C followed by a permutation of the
# three non-control arms, and the six blocks form a position-balanced rotation
# in which every non-control arm occupies each of block positions 2, 3 and 4
# exactly twice -- so no arm is systematically earlier in a block than another.
#   C = all three gates unset                       (shipped kernel = preregistered revert)
#   K = DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1      (packed float2/float4 butterfly reduction)
#   H = DARKBLOOM_FUSED_SLIDING_ATTN_H4=1           (4 query heads per threadgroup, request-side)
#   P = DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1     (attribution instrument; numerically WRONG
#                                                    output by design, passed_correctness=false
#                                                    expected, never a submission candidate)
# Path: ./benchmark.sh --local-submit (1023 decode steps). --local-iterate is
# never used here (Rule 86).
#
# Usage: research/maple-nezuko-r106b-packred-paired.sh [ORDER]
#   ORDER default "CKPHCPHKCHKPCKHPCPKHCHPK" (6 control-anchored blocks of 4;
#   6 paired differences per contrast; declared dof = 5 for D_K, D_H and D_P)
# Env:
#   OUT=<tsv>   row sink (default /tmp/r106b-packred-evidence.tsv; kept outside the
#               worktree so a run never dirties the assignment checkout)
#   BLOCK=<n>   runs per block for the block label only (default 4)
#   KEEP=1      keep the per-run score json copies in /tmp
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-CKPHCPHKCHKPCKHPCPKHCHPK}"
BLOCK="${BLOCK:-4}"
# Fail closed on a stale/mistyped order: only C, K, H and P are defined arms
# here, and an unknown letter would silently fall through to the control branch
# and be recorded under its own label -- i.e. it would fabricate a paired
# difference of zero. Reject it instead.
case "$ORDER" in
  *[!CKHP]*) echo "FATAL: ORDER='$ORDER' contains an arm other than C, K, H or P" >&2; exit 2 ;;
esac
OUT="${OUT:-/tmp/r106b-packred-evidence.tsv}"
SESSION="$(date -u +%Y%m%dT%H%M%SZ)"

# Unattended automation: never offer the interactive fan boost; the 40 C
# thermal cool gate still waits and still fails closed before each timed phase.
export MLXFAST_LOCAL_FAN_PROMPT=0

if [ ! -s "$OUT" ]; then
  printf 'session\tidx\tblock\tarm\tkernel\tdecode_s_per_token\tprefill_s_per_token\tpassed\twall_s\terror\n' > "$OUT"
fi

# Gate provenance. The four sliding-attention kernels are lazily initialised
# globals, each referenced from exactly one arm of the selection ladder, and
# each announces its own MLX kernel name once at construction. So the run log
# names the kernel the process actually compiled -- independent of what this
# script believes it exported. Arm K is bit-identical to the control in both
# geometry and output, so this line is the only way to tell a real PACKRED run
# from a stale binary or a mistyped gate; the campaign fails closed on a
# mismatch rather than recording a fabricated near-zero paired difference.
expected_kernel() {
  case "$1" in
    K) echo laguna_sliding_fused_attn_ring_packred_v1 ;;
    H) echo laguna_sliding_fused_attn_ring_h4_v1 ;;
    P) echo laguna_sliding_fused_attn_ring_noreduce_v1 ;;
    *) echo laguna_sliding_fused_attn_ring_v1 ;;
  esac
}
observed_kernel() {
  grep -o 'laguna_sliding_fused_attn_ring[a-z0-9_]*' "$1" 2>/dev/null \
    | sort -u | paste -sd, -
}

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  block=$(( (i + BLOCK - 1) / BLOCK ))
  log="/tmp/r106b_packred_paired_${SESSION}_${i}${arm}.log"
  score="/tmp/r106b_packred_paired_${SESSION}_${i}${arm}.score.json"
  rm -f score.json
  echo "=== paired arm=${arm} block=${block} idx=${i} start $(date -u +%H:%M:%S)"
  t0=$(date +%s)
  case "$arm" in
    K) DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1 ./benchmark.sh --local-submit > "$log" 2>&1 ;;
    H) DARKBLOOM_FUSED_SLIDING_ATTN_H4=1 ./benchmark.sh --local-submit > "$log" 2>&1 ;;
    P) DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1 ./benchmark.sh --local-submit > "$log" 2>&1 ;;
    *) ./benchmark.sh --local-submit > "$log" 2>&1 ;;
  esac
  rc=$?
  wall=$(( $(date +%s) - t0 ))
  git checkout -q -- Package.resolved 2>/dev/null || true
  want="$(expected_kernel "$arm")"
  got="$(observed_kernel "$log")"
  if [ "$got" != "$want" ]; then
    echo "FATAL: arm=${arm} idx=${i} gate provenance mismatch:" >&2
    echo "  expected kernel '${want}' but the run log named '${got:-<none>}'" >&2
    echo "  see ${log}" >&2
    exit 1
  fi
  if [ ! -f score.json ]; then
    # Arm P is a deliberately incorrect attribution instrument. If the harness
    # refuses to emit a score for it, that costs the secondary contrast only and
    # must NOT destroy the primary C-vs-K campaign, so record the miss and go on.
    if [ "$arm" = "P" ]; then
      echo "WARN: arm=P idx=${i} produced no score.json (rc=${rc}); see ${log}" >&2
      printf '%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%d\t%s\n' \
        "$SESSION" "$i" "$block" "$arm" "$got" NA NA NA "$wall" "no-score-json-rc=${rc}" | tee -a "$OUT"
      continue
    fi
    echo "FATAL: arm=${arm} idx=${i} produced no score.json (rc=${rc}); see ${log}" >&2
    tail -20 "$log" >&2
    exit 1
  fi
  cp score.json "$score"
  dec=$(jq -r '.metrics.decode_seconds_per_token // "NA"' "$score")
  pre=$(jq -r '.metrics.prefill_seconds_per_token // "NA"' "$score")
  pas=$(jq -r '.metrics.passed_correctness // "NA"' "$score")
  err=$(jq -r '.metrics.error // ""' "$score")
  printf '%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%d\t%s\n' \
    "$SESSION" "$i" "$block" "$arm" "$got" "$dec" "$pre" "$pas" "$wall" "$err" | tee -a "$OUT"
  echo "=== paired arm=${arm} block=${block} idx=${i} done  $(date -u +%H:%M:%S) rc=${rc} wall=${wall}s"
  [ "${KEEP:-0}" = 1 ] || rm -f "$score"
done

rm -f score.json
echo "--- $OUT ---"
cat "$OUT"
