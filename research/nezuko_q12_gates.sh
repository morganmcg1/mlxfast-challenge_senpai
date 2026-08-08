#!/usr/bin/env bash
# Q12 (PR #441) pre-submission correctness gates for the decode router block
# tournament. Research-only; sequential because only one model-holding process
# may run at a time.
#
#   bash research/nezuko_q12_gates.sh /tmp/nezq12/gates
#
# Runs, in order:
#   1. the public 64-step drift tripwire once per arm (off / on / inert), so the
#      guard-ON candidate and the rule-3 inert control are both gated, not just
#      the shipped default;
#   2. `research/run_upstream_equivalence.sh`, which must report a NON-ZERO
#      selected-test count (rule 35: it is structurally blind to the fused-weight
#      family, so a pass here is necessary but not sufficient).
set -uo pipefail
cd "$(dirname "$0")/.."

OUTDIR="${1:?outdir}"
WORKER="${MLXFAST_RUNTIME_WORKER_EXECUTABLE:-$PWD/.build-worker/release/mlxfast-runtime-worker}"
CLI="${CLI:-$PWD/.build/release/mlxfast-swift}"
GOLDEN="${GOLDEN:-correctness_prompts/public_longcopy_gate_english_512_256.json}"
[[ -x "$WORKER" ]] || { echo "missing worker: $WORKER" >&2; exit 2; }
[[ -x "$CLI" ]] || { echo "missing cli: $CLI" >&2; exit 2; }
export MLXFAST_RUNTIME_WORKER_EXECUTABLE="$WORKER"
mkdir -p "$OUTDIR"

bad=0
for arm in off on inert; do
  case "$arm" in
    off)   flag=0 ;;
    on)    flag=1 ;;
    inert) flag=inert ;;
  esac
  echo "=== $(date -u +%H:%M:%S) golden tripwire arm=${arm} DARKBLOOM_DECODE_ROUTER_TOURNAMENT=${flag}"
  MLXFAST_NO_SANDBOX=1 \
  DARKBLOOM_DECODE_ROUTER_TOURNAMENT="${flag}" \
    "$CLI" correctness --weights weights --golden "$GOLDEN" \
    > "${OUTDIR}/golden_${arm}.json" 2> "${OUTDIR}/golden_${arm}.err"
  rc=$?
  ARM="${arm}" RC="${rc}" JSON="${OUTDIR}/golden_${arm}.json" python3 - <<'PY' || bad=1
import json, os, sys
arm, rc = os.environ["ARM"], os.environ["RC"]
raw = open(os.environ["JSON"]).read()
row = {}
i = raw.find("{")
if i >= 0:
    try:
        row, _ = json.JSONDecoder().raw_decode(raw[i:])
    except Exception as exc:
        print(f"  arm={arm}: unparseable gate output: {exc}", file=sys.stderr)
passed = row.get("passed")
print(f"  arm={arm:<5s} rc={rc} passed={passed} "
      f"checked_steps={row.get('checked_steps')} "
      f"cases={row.get('case_count')} "
      f"first_failing_case={row.get('first_failing_case')} "
      f"first_failing_step={row.get('first_failing_step')} "
      f"golden_hash={str(row.get('golden_hash'))[:16]} "
      f"error={row.get('error')!r}")
if not (passed is True and rc == "0"):
    print(f"  arm={arm}: GATE FAILED", file=sys.stderr)
    sys.exit(1)
PY
done

echo "=== $(date -u +%H:%M:%S) upstream equivalence oracle"
bash research/run_upstream_equivalence.sh > "${OUTDIR}/equivalence.log" 2>&1
eq=$?
tail -n 20 "${OUTDIR}/equivalence.log"
grep -E '^EQUIVALENCE_(EXACT_STEPS|EXIT)=' "${OUTDIR}/equivalence.log" || true
tests="$(grep -cE 'Test lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled\(\) passed' "${OUTDIR}/equivalence.log")"
echo "EQUIVALENCE_SELECTED_TESTS_PASSED=${tests}"
if [[ "$eq" -ne 0 || "$tests" -eq 0 ]]; then
  echo "equivalence: FAIL (rc=${eq} tests_passed=${tests})" >&2
  bad=1
fi

git checkout -- Package.resolved 2>/dev/null || true
echo "=== gates done $(date -u +%H:%M:%S) fail=${bad}"
exit "$bad"
