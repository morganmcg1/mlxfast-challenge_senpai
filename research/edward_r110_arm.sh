#!/bin/bash
# One paired-timing arm for r110-b rev3: rebuild the AOT metallib so both arms
# are built identically, run --local-iterate, and archive the score under a tag.
set -u
cd "$(dirname "$0")/.." || exit 1
tag="${1:?usage: edward_r110_arm.sh <tag>}"
out="research/maple-edward-r110/logs/score-${tag}.json"

./tools/build-mlx-metallib.sh || exit 1
./benchmark.sh --local-iterate || exit 1
cp score.local-iterate.json "${out}" || exit 1

python3 - "${out}" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))["metrics"]
d, p = m["decode_seconds_per_token"], m["prefill_seconds_per_token"]
ns = (0.013890 / d) ** 0.75 * (0.0003845 / p) ** 0.25
print(f"ARM commit={m['commit']} decode={d!r} prefill={p!r} "
      f"ns={ns:.6f} correct={m['passed_correctness']}")
PY
