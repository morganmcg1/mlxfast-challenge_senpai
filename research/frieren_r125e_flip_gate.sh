#!/usr/bin/env bash
# R125-E correctness gate for a compiled-default flip already applied to the
# worktree. Runs the scored harness (which rebuilds the worker), the upstream
# oracle, and the editable-surface budget check. One model-holding process only.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

OUT=${OUT:-/tmp/r125e-flip}
BASE_SHA=${BASE_SHA:-1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7}
mkdir -p "${OUT}"
export PATH="${HOME}/.local/bin:${PATH}"
export MLXFAST_LOCAL_FAN_PROMPT=0

echo "### worktree diff vs HEAD~ $(date -u +%H:%M:%SZ)"
git --no-pager diff HEAD~1 -- Sources | sed 's/^/DIFF /'

echo "### editable budget $(date -u +%H:%M:%SZ)"
senpai/check-editable-budget.sh "${BASE_SHA}" 2>&1 | sed 's/^/BUDGET /'

echo "### local-iterate (rebuilds worker, paired baseline+candidate) $(date -u +%H:%M:%SZ)"
./benchmark.sh --local-iterate > "${OUT}/iter.log" 2>&1
echo "### local-iterate exit=$?"
if [ -f score.local-iterate.json ]; then
    cp -f score.local-iterate.json "${OUT}/score.json"
    python3 - "${OUT}/score.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
m = d.get("metrics", {})
for name in ["decode_seconds_per_token", "prefill_seconds_per_token",
             "baseline_decode_seconds_per_token",
             "baseline_prefill_seconds_per_token",
             "decode_speedup", "prefill_speedup",
             "passed_decode_speedup_floor", "passed_prefill_speedup_floor",
             "passed_correctness", "max_abs_diff", "golden_hash",
             "checked_steps", "error"]:
    print(f"SCORE {name}={m.get(name)}")
print(f"SCORE score={d.get('score')} passed={d.get('passed')}")
PY
else
    echo "SCORE missing score.local-iterate.json"
fi
grep -E -i 'speedup|correctness|drift|tripwire|golden|FAIL' "${OUT}/iter.log" | tail -40

echo "### upstream equivalence $(date -u +%H:%M:%SZ)"
EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh \
    > "${OUT}/equiv.log" 2>&1
echo "### equivalence wrapper exit=$?"
grep -E 'EQUIVALENCE_EXACT_STEPS|EQUIVALENCE_EXIT|zero selected tests|Executed' \
    "${OUT}/equiv.log" | sed 's/^/EQUIV /'
git checkout -- Package.resolved 2>/dev/null || true

echo "### done $(date -u +%H:%M:%SZ)"
