#!/bin/bash
# R106-J Stage 1: paired ABBA between T0 (advisor-HEAD Sources) and T1
# (4b0e051b Sources) on one fixed vendor tree.
#
# Arm switching is a partial-tree checkout of the two Sources/ grants only, so
# every arm shares one identical Vendor/** and one identical mlx.metallib. The
# worktree is intentionally dirty while the sweep runs and is restored to the
# arm named by RESTORE_ARM at the end.
#
# Usage: abba_t0_t1.sh <blocks> [RESTORE_ARM]
#   blocks=2 -> T0 T1 T1 T0 T1 T0 T0 T1  (2 ABBA blocks, 8 runs)

set -u

T0_SHA="446fe9875d1f95b1216628b5809a99da844e5c79"
T1_SHA="4b0e051bf3cd9777bd6d2be64e172c490705f9a5"
PATHS=(Sources/MLXFastModel Sources/MLXFastTransform)

blocks="${1:-2}"
restore_arm="${2:-T1}"

root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$root" || exit 3
art="$root/research/artifacts/maple-fern-r106j/abba"
mkdir -p "$art"
tsv="$art/runs.tsv"
[ -f "$tsv" ] || printf 'idx\tarm\tstarted_utc\twall_s\trc\tdecode_s_per_token\tprefill_s_per_token\tpassed\tmax_abs_diff\tgolden_hash\tworker_sha256\n' > "$tsv"

select_arm() {
  local sha="$1"
  rm -rf "${PATHS[@]}" || return 4
  git checkout "$sha" -- "${PATHS[@]}" || return 5
  local n
  n=$(git diff --numstat "$sha" -- "${PATHS[@]}" | wc -l | tr -d ' ')
  if [ "$n" != "0" ]; then
    echo "[abba] FATAL: arm $sha not exactly materialised ($n differing files)" >&2
    return 6
  fi
  return 0
}

# A run whose arm equals the previous run's skips the Swift recompile, so it
# also skips ~40 s of incidental GPU cooldown and measures systematically
# slower. That slot sits at position 3 of every block, so the block phase must
# continue across invocations or the slot is handed to one arm more often than
# the other.
done_rows=$(($(wc -l < "$tsv") - 1))
phase=$(((done_rows / 4) % 2))

seq_arms=()
for ((b = 0; b < blocks; b++)); do
  if (( (b + phase) % 2 == 0 )); then
    seq_arms+=(T0 T1 T1 T0)
  else
    seq_arms+=(T1 T0 T0 T1)
  fi
done

idx=$done_rows
for arm in "${seq_arms[@]}"; do
  idx=$((idx + 1))
  sha="$T0_SHA"
  [ "$arm" = "T1" ] && sha="$T1_SHA"
  echo "[abba] run $idx arm=$arm sha=$sha"
  select_arm "$sha" || exit $?

  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  start=$(date +%s)
  ./benchmark.sh --local-iterate > "$art/run${idx}.${arm}.log" 2>&1
  rc=$?
  wall=$(($(date +%s) - start))

  cp score.local-iterate.json "$art/run${idx}.${arm}.json" 2>/dev/null
  worker=".build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker"
  wsha="missing"
  [ -f "$worker" ] && wsha="$(shasum -a 256 "$worker" | cut -d' ' -f1)"

  read -r dec pre passed mad gh <<EOF
$(python3 - "$art/run${idx}.${arm}.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("nan nan nan nan nan"); raise SystemExit
def g(*keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return "nan"
        cur = cur[k]
    return cur
flat = {}
def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, k)
    else:
        flat.setdefault(p, o)
walk(d)
print(flat.get("decode_seconds_per_token", "nan"),
      flat.get("prefill_seconds_per_token", "nan"),
      flat.get("passed", "nan"),
      flat.get("max_abs_diff", "nan"),
      str(flat.get("golden_hash", "nan"))[:16])
PY
)
EOF

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$idx" "$arm" "$started" "$wall" "$rc" "$dec" "$pre" "$passed" "$mad" "$gh" "$wsha" >> "$tsv"
  echo "[abba] run $idx arm=$arm rc=$rc decode=$dec prefill=$pre passed=$passed"
done

restore_sha="$T1_SHA"
[ "$restore_arm" = "T0" ] && restore_sha="$T0_SHA"
select_arm "$restore_sha" || exit 7
git checkout -- Package.resolved 2>/dev/null
# select_arm stages its checkout; without this the index re-adds paths the
# restored arm deletes and a later `git commit -a` would silently revive them.
git reset -q
echo "[abba] restored arm=$restore_arm"
column -t -s $'\t' "$tsv"
