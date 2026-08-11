#!/usr/bin/env bash
# fern R109-F: measure an env-knob arm against the current build.
#
# Many darkbloom arms are exposed as DARKBLOOM_* environment knobs read once at
# first use (e.g. lagunaRouterWeightPrefetch reads
# DARKBLOOM_ROUTER_WEIGHT_PREFETCH). For those arms a rebuild is pure waste:
# the same binary can be measured under a different knob value in the 155 s the
# benchmark itself takes, instead of the ~4 min a build-plus-benchmark cycle
# costs. Use research/fern_r109f_ab_rebuild.sh when the arm needs a code change.
#
# Usage: research/fern_r109f_env_bench.sh <label> VAR=VAL [VAR=VAL ...]
#
# Leaves the archived score at research/artifacts/fern-r109f/ab/score.<label>.json
# so env arms and code arms land in one comparable ledger.
set -uo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <label> VAR=VAL [VAR=VAL ...]" >&2
    exit 2
fi

label="$1"
shift

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

out_dir="research/artifacts/fern-r109f/ab"
mkdir -p "$out_dir"

echo "=== [$label] worktree provenance ==="
git rev-parse HEAD
git status --porcelain | head -20

echo "=== [$label] env arm ==="
for kv in "$@"; do
    case "$kv" in
        *=*) ;;
        *) echo "not a VAR=VAL assignment: $kv" >&2; exit 2 ;;
    esac
    echo "  export $kv"
    export "$kv"
done

# No build step on purpose: the point of this script is that the binary under
# test is byte-identical to the one the previous arm measured, so the only
# difference between the two rows of the ledger is the knob.
echo "=== [$label] local-iterate benchmark (no rebuild) ==="
bash benchmark.sh --local-iterate
rc=$?

if [ -f score.local-iterate.json ]; then
    cp score.local-iterate.json "$out_dir/score.$label.json"
    echo "=== [$label] archived $out_dir/score.$label.json ==="
    python3 - "$out_dir/score.$label.json" "$label" <<'PY'
import json, sys
path, label = sys.argv[1], sys.argv[2]
m = json.load(open(path))["metrics"]
print(
    f"{label:28s} decode {m['decode_seconds_per_token']:.6f} s/tok  "
    f"prefill {m['prefill_seconds_per_token']:.6f} s/tok  "
    f"correct={m['passed_correctness']}  golden={m['golden_hash'][:16]}"
)
PY
else
    echo "=== [$label] NO SCORE FILE PRODUCED (rc=$rc) ===" >&2
fi

exit "$rc"
