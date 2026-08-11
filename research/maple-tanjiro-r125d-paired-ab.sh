#!/bin/bash
# R125-D paired A/B: same worker binary, one env lever
# (DARKBLOOM_EXPERT_DOWN_BN in {128 candidate, 64 baseline}), alternating arms
# so drift is shared. On an Apple GPU generation < 17 host the lever is inert by
# construction (gather_qmm_rhs_nax is unreachable), so this run is a
# decode-neutrality and correctness guard, not prefill evidence.
set -u
cd "$(dirname "$0")/.." || exit 1
OUT="research/artifacts/tanjiro-r125d"
REPS="${REPS:-2}"
mkdir -p "${OUT}"

for rep in $(seq 1 "${REPS}"); do
    for bn in 128 64; do
        echo "=== rep ${rep} arm bn=${bn} $(date -u +%FT%TZ) ==="
        DARKBLOOM_EXPERT_DOWN_BN="${bn}" ./benchmark.sh --local-iterate || exit 1
        cp score.local-iterate.json "${OUT}/score-bn${bn}-rep${rep}.json"
    done
done

python3 - "${OUT}" "${REPS}" <<'PY'
import json, statistics, sys
out, reps = sys.argv[1], int(sys.argv[2])
arms = {}
for bn in (128, 64):
    rows = []
    for r in range(1, reps + 1):
        m = json.load(open(f"{out}/score-bn{bn}-rep{r}.json"))["metrics"]
        rows.append(m)
    arms[bn] = rows
print(f"{'metric':38}{'bn=128 (cand)':>18}{'bn=64 (base)':>18}")
for k in ("decode_seconds_per_token", "prefill_seconds_per_token",
          "decode_speedup", "prefill_speedup"):
    c = [r[k] for r in arms[128]]
    b = [r[k] for r in arms[64]]
    print(f"{k:38}{statistics.fmean(c):>18.9f}{statistics.fmean(b):>18.9f}")
for k in ("passed_correctness", "checked_steps", "max_abs_diff", "golden_hash"):
    c = {str(r[k]) for r in arms[128]}
    b = {str(r[k]) for r in arms[64]}
    print(f"{k:38}{','.join(sorted(c))[:18]:>18}{','.join(sorted(b))[:18]:>18}")
dc = statistics.fmean([r["decode_seconds_per_token"] for r in arms[128]])
db = statistics.fmean([r["decode_seconds_per_token"] for r in arms[64]])
print(f"\ndecode s/token candidate/baseline = {dc/db:.6f}  (1.0 == neutral)")
json.dump(arms, open(f"{out}/paired-ab.json", "w"), indent=1, sort_keys=True)
print(f"wrote {out}/paired-ab.json")
PY
