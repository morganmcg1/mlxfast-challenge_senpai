#!/usr/bin/env bash
# R119-B correctness gate: env-gated scored benchmark (OFF/ON) + upstream oracle.
# One model-holding process at a time; never run alongside the ABBA campaign.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

OUT=${OUT:-/tmp/r119b-correct}
mkdir -p "${OUT}"
export PATH="${HOME}/.local/bin:${PATH}"
# The fan prompt blocks an unattended worker; the thermal gate is untouched.
export MLXFAST_LOCAL_FAN_PROMPT=0

report_score() {
    local tag="$1" file="$2"
    python3 - "$tag" "$file" <<'PY'
import json, sys
tag, path = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(path))
except Exception as exc:
    print(f"SCORE {tag} unreadable: {exc}")
    raise SystemExit(0)
m = d.get("metrics", {})
names = [
    "decode_seconds_per_token", "prefill_seconds_per_token",
    "baseline_decode_seconds_per_token", "baseline_prefill_seconds_per_token",
    "decode_speedup", "prefill_speedup",
    "passed_decode_speedup_floor", "passed_prefill_speedup_floor",
    "passed_correctness", "max_abs_diff", "golden_hash", "harness_hash",
    "checked_steps", "num_layers", "commit", "error", "timestamp",
]
for name in names:
    print(f"SCORE {tag} {name}={m.get(name)}")
print(f"SCORE {tag} score={d.get('score')} passed={d.get('passed')}")
PY
}

for gate in 0 1; do
    echo "### local-iterate gate=${gate} $(date -u +%H:%M:%SZ)"
    DARKBLOOM_SHARED_ROUTED_QMV_FUSED="${gate}" ./benchmark.sh --local-iterate \
        > "${OUT}/iter_${gate}.log" 2>&1
    rc=$?
    echo "### local-iterate gate=${gate} exit=${rc}"
    if [ -f score.local-iterate.json ]; then
        cp -f score.local-iterate.json "${OUT}/score_${gate}.json"
        report_score "gate${gate}" "${OUT}/score_${gate}.json"
    else
        echo "SCORE gate${gate} missing score.local-iterate.json"
    fi
    grep -E -i 'speedup|correctness|drift|tripwire|band|FAIL|golden' \
        "${OUT}/iter_${gate}.log" | tail -40
done

echo "### upstream equivalence gate=1 $(date -u +%H:%M:%SZ)"
DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1 research/run_upstream_equivalence.sh \
    > "${OUT}/equiv_on.log" 2>&1
echo "### equivalence wrapper exit=$?"
grep -E 'EQUIVALENCE_EXACT_STEPS|EQUIVALENCE_EXIT|zero selected tests' "${OUT}/equiv_on.log"
git checkout -- Package.resolved 2>/dev/null || true

echo "### done $(date -u +%H:%M:%SZ)"
