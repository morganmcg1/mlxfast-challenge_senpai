#!/usr/bin/env bash
# R106-B: independent audit of the paired evidence table against the raw run logs.
#
# Why this exists.  The paired runner reads score.json through
#   jq -r '.metrics.passed_correctness // "NA"'
# and jq's `//` alternative operator fires on `false` as well as on `null`, so a
# genuine `passed_correctness: false` is written to the table as `NA`.  The
# correctness column is therefore ambiguous between "false" and "absent".  This
# script re-derives, straight out of each per-run log,
#
#   * the Metal kernel name the binary announced (Rule 33 provenance),
#   * passed_correctness as the harness itself printed it,
#   * decode_seconds_per_token,
#
# and diffs them against the table.  Any disagreement is a hard failure: the
# paired contrasts in the report must not be computed from a table that does not
# match its own logs.
#
# usage: research/maple-nezuko-r106b-verify-evidence-rows.sh <evidence.tsv> [logdir]
set -uo pipefail

TSV="${1:?usage: $0 <evidence.tsv> [logdir]}"
LOGDIR="${2:-/tmp}"
fail=0

printf 'idx\tarm\ttsv_kernel\tlog_kernel\ttsv_passed\tlog_passed\ttsv_decode\tlog_decode\tverdict\n'

while IFS=$'\t' read -r session idx block arm kernel dec pre pas wall err; do
  [ "$session" = session ] && continue
  log="${LOGDIR}/r106b_packred_paired_${session}_${idx}${arm}.log"
  if [ ! -f "$log" ]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$idx" "$arm" "$kernel" MISSING-LOG "$pas" - "$dec" - FAIL
    fail=1
    continue
  fi

  # Rule 33 provenance: the kernel's own one-shot initialiser writes this once.
  lk=$(grep -o 'sliding fused attn kernel: [a-z0-9_]*' "$log" | tail -1 | sed 's/.*: //')
  [ -n "$lk" ] || lk=NONE

  # passed_correctness straight from the harness's own summary line.
  lp=$(grep -o 'checked timing complete passed=[a-z]*' "$log" | tail -1 | sed 's/.*=//')
  [ -n "$lp" ] || lp=NONE

  # decode figure straight from the harness's own summary line.
  ld=$(grep -o 'local-submit summary decode_seconds_per_token=[0-9.]*' "$log" \
        | tail -1 | sed 's/.*=//')
  [ -n "$ld" ] || ld=NONE

  v=OK
  [ "$lk" = "$kernel" ] || v=FAIL-KERNEL
  # The table's `true` must agree with the log; the table's `NA` must correspond
  # to a log that says false (the jq `//` swallow) and never to one that says true.
  case "$pas:$lp" in
    true:true) : ;;
    NA:false)  : ;;
    *)         v="${v}/FAIL-PASSED" ;;
  esac
  # The summary line is printf "%.6f", so the table's full-precision figure must
  # be re-rounded the same way before comparing; a prefix match is wrong whenever
  # the sixth decimal rounds up (0.009006960... prints as 0.009007).
  if [ "$dec" = NA ]; then
    [ "$ld" = NONE ] || v="${v}/FAIL-DECODE"
  elif [ "$ld" = NONE ]; then
    v="${v}/FAIL-DECODE"
  else
    awk -v a="$dec" -v b="$ld" 'BEGIN{exit !(sprintf("%.6f",a)==sprintf("%.6f",b))}' \
      || v="${v}/FAIL-DECODE"
  fi
  case "$v" in OK) : ;; *) fail=1 ;; esac

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$idx" "$arm" "$kernel" "$lk" "$pas" "$lp" "$dec" "$ld" "$v"
done < "$TSV"

if [ "$fail" -ne 0 ]; then
  echo "VERIFY: FAIL -- the evidence table disagrees with its own run logs" >&2
  exit 1
fi
echo "VERIFY: OK -- every row's kernel name, correctness flag and decode figure match its log"
