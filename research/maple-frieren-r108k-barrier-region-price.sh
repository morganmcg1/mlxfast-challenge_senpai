#!/usr/bin/env bash
# R108-K — THE BARRIER-REGION PRICE PROBE (PR #660 comment 6, 16:31Z).
#
# The advisor asked for a two-arm probe: N no-op dispatches per decode step whose
# only input is a buffer NOT in the encoder's prev_outputs_ (arm F, "free
# region", no memoryBarrier), versus the same N no-ops chained so that every one
# reads its predecessor's output and therefore forces
# CommandEncoder::maybeInsertBarrier() to emit memoryBarrier(BarrierScopeBuffers)
# (arm S, "serialising").
#
# THAT INSTRUMENT IS ALREADY IN THE BASE TREE and needs zero Sources bytes:
#   Sources/MLXFastModel/LagunaRuntimeModel.swift:12040 lagunaInjectEmptyKernel
#     name laguna_inject_empty_dispatch_v1, inputs ["control","prev"], output
#     ["sink"], body writes nothing (guarded on control[0]==0xFFFFFFFF).
#   :12105 lagunaInjectLayerWork(layer:isSingleTokenDecode:) emits `empties`
#     copies per layer and finalises them with asyncEval(pending).
#   :12130 the `prev` binding is EXACTLY the advisor's dependency edge:
#       lagunaInjectEmptyChain ? tail : scratch.control[7]
#     CHAIN=1 -> prev is the previous no-op's OUTPUT  => RAW hazard => barrier
#     CHAIN=0 -> prev is scratch.control[7], a constant materialised once in
#                LagunaInjectStore.scratch's eval() and never written by a
#                kernel again => never in prev_outputs_ => NO barrier.
#   So: arm F == DARKBLOOM_INJECT_EMPTY_CHAIN=0, arm S == CHAIN=1 (the default,
#   and therefore the configuration Rule 65's +2.3403 M5 us/dispatch was
#   measured in).
#
# Both arms are byte-matched, grid-matched and threadgroup-matched by
# construction (same kernel, same DARKBLOOM_INJECT_EMPTY_TG, same count, same
# per-layer asyncEval); only the dependency edge differs. Both are
# correctness-green by construction (the sink is never read by the model).
#
# ARMS (all through ./benchmark.sh --local-submit, 1023 decode steps; Rule 86
# forbids --local-iterate as evidence).
#   C control : no injection at all
#   F free    : EMPTY=160  TG=8 CHAIN=0  (+4 unchained no-ops per layer)
#   S serial  : EMPTY=160  TG=8 CHAIN=1  (+4 chained no-ops per layer)
#   H hi-free : EMPTY=1200 TG=8 CHAIN=0  (+30 unchained no-ops per layer)
#   J hi-ser  : EMPTY=1200 TG=8 CHAIN=1  (+30 chained no-ops per layer)
#   G gauge   : EMPTY=2400 TG=8 CHAIN=1  POSITIVE CONTROL, run FIRST.
#
# WHY TWO RUNGS AND NOT ONE. r93-A (research/r93-runs/knee-results.md) already
# measured the CHAINED ladder on this host and this tree: K=240 and K=480 are
# FREE (segment slopes -0.43 and -0.03 M4 us/dispatch) and the curve only turns
# positive past ~480 (+0.58, +0.73, +1.98, +2.36). So r93-A predicts that arm S
# at N=160 is free TOO, and a null there would say nothing about barriers. The
# 160 rung therefore answers the DECISION question (what does a dispatch cost
# where production actually sits, ~411 dispatches/step) and the 1200 rung
# answers the MECHANISM question (r93-A puts the chained 1200 rung at
# +374 us/step; if H is null while J reproduces +374, the barrier IS the price
# and the launch is free, which is the advisor's device.cpp reading confirmed
# end-to-end).
#
# GAUGE. r93-A's K=2400 chained rung measured 11.344 ms vs 8.223 ms at K=0, i.e.
#               +3121 us/step = +38 %. G must reproduce that magnitude. If G is
#               null the environment channel is dead and every other arm is a
#               fabricated zero. G doubles as a cross-epoch replication of
#               r93-A's steepest rung on today's tree. This is
#               the whole provenance guard for the campaign.
#
# Rule 98.9's residency-defeated sensitivity arm is NOT AVAILABLE and is not
# faked: FERN_DEFEAT_SLOTS is a knob of fern's standalone desk microbenchmark
# only (state doc :6204, "exists only in three ..."), it is absent from Sources/
# and from benchmark.sh, so exporting it around ./benchmark.sh would be inert and
# would have manufactured a null sensitivity result. Declared as a limitation.
#
# N = 160 (not 40) is deliberate: the family-E merge removes 40 dispatches/step,
# but nezuko's paired instrument resolves ~24.8 us/step per block, so a 40-wide
# lever cannot be resolved per-dispatch at any affordable block count. 160 gives
# +-0.30/sqrt(B) us/dispatch. Linearity between 40 and 160 is an assumption and
# is declared as one; r93-A's 0->240->480 segments support it (-0.43, -0.03).
#
# TG=8 (not the source default 160) matches the historical M5 ladder receipts
# and r93-A, so the slope here is directly comparable to Rule 65.
#
# Residency is left at whatever ./benchmark.sh does natively in every arm: this
# is an instrument-calibration probe whose whole job is to be commensurable with
# Rule 65, r93-A and #483, all measured the same way.
#
# Usage: research/maple-frieren-r108k-barrier-region-price.sh [ORDER]
#   ORDER default "GCFSCSFCHJCFSCSFCJH": the gauge run, then six
#   control-anchored blocks of three. Blocks 1,2,4,5 are the 160 rung (CFS,CSF,
#   CFS,CSF: F sits in block position 2 twice and position 3 twice, so neither
#   arm is systematically earlier); blocks 3,6 are the 1200 rung (CHJ,CJH, same
#   balance). The 1200 rung is placed at block 3, not last, so that truncating
#   the campaign still leaves one mechanism block. Rows are appended per run, so
#   the campaign may be
#   truncated after any completed block without invalidating the blocks already
#   recorded (declared stopping rule: stop after the last completed block before
#   18:20Z, minimum four blocks).
# Env:
#   OUT=<tsv>  row sink, default /tmp/r108k-barrier-price.tsv (outside the
#              worktree so a run never dirties the assignment checkout)
#   KEEP=1     keep per-run score json copies
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-GCFSCSFCHJCFSCSFCJH}"
case "$ORDER" in
  *[!CFSHJG]*) echo "FATAL: ORDER='$ORDER' has an arm outside C,F,S,H,J,G" >&2; exit 2 ;;
esac
OUT="${OUT:-/tmp/r108k-barrier-price.tsv}"
SESSION="$(date -u +%Y%m%dT%H%M%SZ)"

export MLXFAST_LOCAL_FAN_PROMPT=0

if [ ! -s "$OUT" ]; then
  printf 'session\tidx\tblock\tarm\tinject\tchain\ttg\tdefeat\tdecode_s_per_token\tprefill_s_per_token\tpassed\twall_s\terror\n' > "$OUT"
fi

i=0
rank=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  if [ "$arm" = G ]; then
    block=0
  else
    rank=$((rank+1))
    block=$(( (rank + 2) / 3 ))
  fi
  log="/tmp/r108k_barrier_${SESSION}_${i}${arm}.log"
  score="/tmp/r108k_barrier_${SESSION}_${i}${arm}.score.json"
  rm -f score.json

  inj=0; chain=NA; tg=NA; defeat=0
  case "$arm" in
    C) ;;
    F) inj=160;  chain=0; tg=8 ;;
    S) inj=160;  chain=1; tg=8 ;;
    H) inj=1200; chain=0; tg=8 ;;
    J) inj=1200; chain=1; tg=8 ;;
    G) inj=2400; chain=1; tg=8 ;;
  esac

  echo "=== r108k arm=${arm} block=${block} idx=${i} inj=${inj} chain=${chain} tg=${tg} start $(date -u +%H:%M:%S)"
  t0=$(date +%s)
  if [ "$inj" = 0 ]; then
    ./benchmark.sh --local-submit > "$log" 2>&1
  else
    DARKBLOOM_INJECT_DECODE_EMPTY="$inj" \
    DARKBLOOM_INJECT_EMPTY_TG="$tg" \
    DARKBLOOM_INJECT_EMPTY_CHAIN="$chain" \
      ./benchmark.sh --local-submit > "$log" 2>&1
  fi
  rc=$?
  wall=$(( $(date +%s) - t0 ))
  git checkout -q -- Package.resolved 2>/dev/null || true

  if [ ! -f score.json ]; then
    echo "WARN: arm=${arm} idx=${i} produced no score.json (rc=${rc}); see ${log}" >&2
    tail -20 "$log" >&2
    printf '%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%s\n' \
      "$SESSION" "$i" "$block" "$arm" "$inj" "$chain" "$tg" "$defeat" \
      NA NA NA "$wall" "no-score-json-rc=${rc}" | tee -a "$OUT"
    continue
  fi
  cp score.json "$score"
  dec=$(jq -r '.metrics.decode_seconds_per_token // "NA"' "$score")
  pre=$(jq -r '.metrics.prefill_seconds_per_token // "NA"' "$score")
  pas=$(jq -r '.metrics.passed_correctness // "NA"' "$score")
  err=$(jq -r '.metrics.error // ""' "$score")
  printf '%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%s\n' \
    "$SESSION" "$i" "$block" "$arm" "$inj" "$chain" "$tg" "$defeat" \
    "$dec" "$pre" "$pas" "$wall" "$err" | tee -a "$OUT"
  echo "=== r108k arm=${arm} idx=${i} done $(date -u +%H:%M:%S) rc=${rc} wall=${wall}s"
  [ "${KEEP:-1}" = 1 ] || rm -f "$score"
done

rm -f score.json
echo "--- $OUT ---"
cat "$OUT"
