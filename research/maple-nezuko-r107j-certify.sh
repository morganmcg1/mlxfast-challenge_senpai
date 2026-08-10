#!/usr/bin/env bash
# ============================================================================
# maple-nezuko-r107j-certify.sh
#   Turnkey paired-difference certification harness for LOCAL decode candidates.
#   Round 107-J'. Host: Apple M4 Pro (20 GPU cores, 48 GiB). Epoch: R107.
#   Every number this script emits is a LOCAL MARGINAL quantity on THIS host.
#   It is never a census number and never a receipt number.
#
# WHAT IT DOES
#   Runs a blocked, position-balanced, interleaved campaign over 2..6 arms that
#   differ ONLY by environment gates, then prints the paired-difference CI95 of
#   every non-reference arm against the reference arm.
#
# USAGE
#   research/maple-nezuko-r107j-certify.sh --blocks N LABEL:GATES [LABEL:GATES ...]
#
#   The FIRST arm listed is the reference (baseline); every later arm is
#   differenced against it, block by block. GATES is a comma-separated list of
#   NAME=VALUE assignments, or EMPTY for "set no gates at all".
#
#   Examples
#     # A/A null: same binary, same gates, two labels. 12 blocks = 24 runs.
#     research/maple-nezuko-r107j-certify.sh --blocks 12 A: Ap:
#
#     # certify one candidate against the shipped default, 8 blocks = 16 runs
#     research/maple-nezuko-r107j-certify.sh --blocks 8 C: E:DARKBLOOM_SOME_GATE=1
#
#     # certify two candidates and their SUM on a combined tree, 6 blocks = 24 runs
#     research/maple-nezuko-r107j-certify.sh --blocks 6 \
#        C: E:DARKBLOOM_E=1 A:DARKBLOOM_A=1 S:DARKBLOOM_E=1,DARKBLOOM_A=1
#
#   Env knobs
#     OUT=<tsv>    row sink, default /tmp/r107j-certify-<session>.tsv.
#                  Deliberately OUTSIDE the worktree: a campaign must never
#                  dirty the assignment checkout (run_job requires it clean).
#     KEEP=1       keep the per-run score.json copies in /tmp
#     NOANALYSE=1  collect rows only, do not run the analyser at the end
#     ANALYSER=<p> path to the paired-CI analyser
#                  (default research/maple-nezuko-r107j-paired-ci.py)
#
#   Cost: ~198 s per run on this host (measured R106-B: 24 runs = 4750 s).
#         2 arms x 12 blocks = 24 runs ~= 79 min. 2 x 10 = 20 runs ~= 66 min.
#
# ============================================================================
# GUARD RAILS -- these are the four ways this measurement gets silently wrong,
# and what this script does about each.
# ============================================================================
#
# (1) --local-submit ONLY. NEVER mix --local-submit with --local-iterate.
#     The harness runs 1023 decode steps under --local-submit and 128 under
#     --local-iterate, and reports
#         decode_seconds_per_token = mean_step_seconds + K/N,  K ~= 0.5766 s
#     so the SAME binary reads 8984.5 us/token at N=1023 and ~12926 us/token at
#     N=128 -- a 1.44x scale gap that is pure prefill amortisation, not speed.
#     (Cross-check: maple-fern's --local-iterate decode mean 0.012955773 s/tok
#      / my --local-submit 0.008984501 s/step = 1.442, reproducing the factor
#      from a second operator's data.)
#     Consequences: a difference of two iterate levels and a difference of two
#     submit levels are NOT on the same scale; and iterate is ~3.7x noisier per
#     run than submit, which is exactly why this instrument exists. This script
#     therefore HARDCODES --local-submit and refuses any arm whose gate list
#     mentions iterate.
#
# (2) NEVER divide a local level by a receipt level and call the ratio k.
#     The official receipt amortises the seed prefill over 128 tokens, so
#         4925.255 / 8984.50 = 0.5482
#     is a prefill-amortisation artefact of two different N, NOT the M4->M5
#     transfer factor. k must come from a FIXED-TERM FIT across matched
#     workloads (rule 105.13), not from a ratio of two levels. This script does
#     not compute k at all; the analyser takes k as an explicit argument and
#     prints it next to every %-of-cs figure it derives.
#
# (3) PREFILL IS CHARGED NEUTRAL (rule 105.4). The 1023-step submit level
#     carries a constant +563.6 us/token of amortised prefill (K/N). It cancels
#     exactly in a paired difference between two arms that do not touch prefill.
#     The script records prefill_seconds_per_token for every run and the
#     analyser reports the prefill paired difference as a DIAGNOSTIC: if it is
#     not centred on zero, the decode difference is contaminated and the run is
#     not a clean decode certification.
#
# (4) BLOCKING AND POSITION BALANCE, not two back-to-back batches. The host
#     drifts (thermal gate fires on essentially every run) so an unblocked
#     "all A then all A-prime" layout aliases drift onto the contrast. Arms are
#     interleaved inside a block and the within-block ORDER ROTATES every block,
#     so with blocks a multiple of the arm count every arm occupies every
#     position equally often. The analyser additionally regresses the paired
#     difference on within-block position and reports the residual.
#
# Also, by standing prohibition for this round: never invoke
# senpai/submit-official.sh from here, never request a receipt, and never set
# DARKBLOOM_EXPERT_DOWN_BN. The script fails closed on that gate name.
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

BLOCKS=""
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --blocks) BLOCKS="${2:-}"; shift 2 ;;
    --blocks=*) BLOCKS="${1#*=}"; shift ;;
    -h|--help) sed -n '2,110p' "$0"; exit 0 ;;
    --) shift; while [ $# -gt 0 ]; do ARGS+=("$1"); shift; done ;;
    -*) echo "FATAL: unknown option '$1'" >&2; exit 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

case "$BLOCKS" in
  ''|*[!0-9]*) echo "FATAL: --blocks N is required and must be a positive integer" >&2; exit 2 ;;
esac
[ "$BLOCKS" -ge 1 ] || { echo "FATAL: --blocks must be >= 1" >&2; exit 2; }

NARM=${#ARGS[@]}
if [ "$NARM" -lt 2 ] || [ "$NARM" -gt 6 ]; then
  echo "FATAL: need 2..6 arm specs (LABEL:GATES); got ${NARM}" >&2
  exit 2
fi

LABELS=(); GATES=()
for spec in "${ARGS[@]}"; do
  case "$spec" in
    *:*) : ;;
    *) echo "FATAL: arm spec '${spec}' is not LABEL:GATES (the colon is required; use 'C:' for no gates)" >&2; exit 2 ;;
  esac
  lab="${spec%%:*}"
  gts="${spec#*:}"
  case "$lab" in
    ''|*[!A-Za-z0-9_]*) echo "FATAL: arm label '${lab}' must be non-empty and alphanumeric/underscore" >&2; exit 2 ;;
  esac
  for prev in "${LABELS[@]:-}"; do
    [ "$prev" = "$lab" ] && { echo "FATAL: duplicate arm label '${lab}'" >&2; exit 2; }
  done
  # Guard rail (1): an arm may not smuggle in the other harness mode.
  case "$gts" in
    *iterate*|*ITERATE*) echo "FATAL: arm '${lab}' mentions iterate; this instrument is --local-submit ONLY (guard rail 1)" >&2; exit 2 ;;
  esac
  # Standing round-107 prohibition.
  case "$gts" in
    *DARKBLOOM_EXPERT_DOWN_BN*) echo "FATAL: arm '${lab}' sets DARKBLOOM_EXPERT_DOWN_BN, which is prohibited this round" >&2; exit 2 ;;
  esac
  # Every gate must be a NAME=VALUE assignment.
  if [ -n "$gts" ]; then
    IFS=',' read -r -a _kv <<< "$gts"
    for a in "${_kv[@]}"; do
      case "$a" in
        [A-Za-z_]*=*) : ;;
        *) echo "FATAL: arm '${lab}' gate '${a}' is not NAME=VALUE" >&2; exit 2 ;;
      esac
    done
  fi
  LABELS+=("$lab"); GATES+=("$gts")
done

[ -x ./benchmark.sh ] || { echo "FATAL: ./benchmark.sh not found or not executable in $(pwd)" >&2; exit 2; }

SESSION="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${OUT:-/tmp/r107j-certify-${SESSION}.tsv}"
ANALYSER="${ANALYSER:-research/maple-nezuko-r107j-paired-ci.py}"

# Unattended automation: never offer the interactive fan boost. The 40 C
# thermal cool gate still waits and still fails closed before each timed phase.
export MLXFAST_LOCAL_FAN_PROMPT=0

HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
DIRTY="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

if [ ! -s "$OUT" ]; then
  printf 'session\tidx\tblock\tpos\tarm\tgates\tkernels\tdecode_s_per_token\tprefill_s_per_token\tpassed\tgolden\twall_s\thead\terror\n' > "$OUT"
fi

echo "=== r107j-certify session=${SESSION}"
echo "===   head=${HEAD_SHA} dirty_files=${DIRTY} mode=--local-submit blocks=${BLOCKS} arms=${NARM}"
for k in "${!LABELS[@]}"; do
  echo "===   arm[${k}] label=${LABELS[$k]} gates='${GATES[$k]:-<none>}'$( [ "$k" = 0 ] && echo '   <-- REFERENCE' )"
done
echo "===   rows -> ${OUT}"

# Any kernel name the process announces at construction. Used as a stale-binary
# / mistyped-gate detector: within one session an arm must always compile the
# same kernel set, and the analyser reports the set per arm so a reader can see
# whether the gate did anything at all.
observed_kernels() {
  grep -oE 'laguna_[a-z0-9_]+' "$1" 2>/dev/null | sort -u | paste -sd, -
}
declare -a ARMKERN
for k in "${!LABELS[@]}"; do ARMKERN[$k]=""; done

i=0
for (( b=1; b<=BLOCKS; b++ )); do
  # Position balance: rotate the within-block order by (b-1) mod NARM.
  rot=$(( (b - 1) % NARM ))
  for (( p=0; p<NARM; p++ )); do
    k=$(( (p + rot) % NARM ))
    arm="${LABELS[$k]}"; gts="${GATES[$k]}"
    i=$((i+1))
    pos=$((p+1))
    tag="/tmp/r107j_${SESSION}_${i}_${arm}"
    log="${tag}.log"; score="${tag}.score.json"
    rm -f score.json score.local-iterate.json
    echo "=== run idx=${i} block=${b} pos=${pos} arm=${arm} start $(date -u +%H:%M:%S)"
    t0=$(date +%s)
    if [ -n "$gts" ]; then
      IFS=',' read -r -a _kv <<< "$gts"
      env "${_kv[@]}" ./benchmark.sh --local-submit > "$log" 2>&1
    else
      ./benchmark.sh --local-submit > "$log" 2>&1
    fi
    rc=$?
    wall=$(( $(date +%s) - t0 ))
    # benchmark.sh can rewrite Package.resolved; keep the checkout clean.
    git checkout -q -- Package.resolved 2>/dev/null || true

    got="$(observed_kernels "$log")"
    if [ -z "${ARMKERN[$k]}" ]; then
      ARMKERN[$k]="$got"
    elif [ "${ARMKERN[$k]}" != "$got" ]; then
      echo "FATAL: arm=${arm} idx=${i} kernel set changed within the session:" >&2
      echo "  first saw '${ARMKERN[$k]}'" >&2
      echo "  now saw   '${got:-<none>}'" >&2
      echo "  a gate is flaky or the binary changed under us; see ${log}" >&2
      exit 1
    fi

    # Guard rail (1) enforced at the evidence level too: --local-submit writes
    # score.json; --local-iterate writes score.local-iterate.json. If the
    # iterate sink appeared, the mode was not what we asked for.
    if [ -f score.local-iterate.json ]; then
      echo "FATAL: idx=${i} produced score.local-iterate.json; the harness ran in iterate mode (guard rail 1)" >&2
      exit 1
    fi
    if [ ! -f score.json ]; then
      echo "FATAL: idx=${i} arm=${arm} produced no score.json (rc=${rc}); see ${log}" >&2
      tail -25 "$log" >&2
      exit 1
    fi
    cp score.json "$score"
    dec=$(jq -r '.metrics.decode_seconds_per_token // "NA"' "$score")
    pre=$(jq -r '.metrics.prefill_seconds_per_token // "NA"' "$score")
    # NOTE: `// "NA"` swallows a literal false. Use tostring so a real
    # correctness FAILURE is recorded as "false" and not mistaken for missing.
    pas=$(jq -r 'if .metrics.passed_correctness == null then "NA" else (.metrics.passed_correctness|tostring) end' "$score")
    gld=$(jq -r '(.metrics.golden_hash // .golden_hash // "NA")|tostring' "$score")
    err=$(jq -r '(.metrics.error // .error // "")|tostring' "$score")
    printf '%s\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%s\t%s\n' \
      "$SESSION" "$i" "$b" "$pos" "$arm" "${gts:-none}" "${got:-none}" \
      "$dec" "$pre" "$pas" "$gld" "$wall" "${HEAD_SHA:0:12}" "$err" | tee -a "$OUT"
    echo "=== run idx=${i} done $(date -u +%H:%M:%S) rc=${rc} wall=${wall}s"
    [ "${KEEP:-0}" = 1 ] || rm -f "$score"
  done
done

rm -f score.json score.local-iterate.json
echo "--- ${OUT} ---"
cat "$OUT"

if [ "${NOANALYSE:-0}" != 1 ] && [ -f "$ANALYSER" ]; then
  echo
  echo "=== paired CI ==="
  python3 "$ANALYSER" "$OUT" || echo "WARN: analyser exited non-zero" >&2
fi
