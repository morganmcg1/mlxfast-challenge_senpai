#!/bin/bash
# R106-J Stage 2: generalised paired ABBA between any two integration arms.
#
# An arm is a Sources/ tree identity, optionally with the packing-default-flip
# patch applied on top:
#   T0  = advisor HEAD Sources                (446fe987)
#   T1  = 4b0e051b Sources                    (partial replay, Rule 95.6)
#   T0P = T0 + tanjiro_packing_default_flip
#   T1P = T1 + tanjiro_packing_default_flip
#   T0U = T0 + r106j/t0u_unroll_depth.patch   (T1's 2-deep sliding ring only)
#
# Every arm shares one identical Vendor/** and one identical mlx.metallib, so
# the contrast is exactly the Sources/ difference. The worktree is dirty while
# the sweep runs and is restored to RESTORE_ARM at the end.
#
# Usage: abba_arms.sh <armA> <armB> <blocks> <RESTORE_ARM> <tag>

set -u

T0_SHA="446fe9875d1f95b1216628b5809a99da844e5c79"
T1_SHA="4b0e051bf3cd9777bd6d2be64e172c490705f9a5"
PATHS=(Sources/MLXFastModel Sources/MLXFastTransform)
TARGET="Sources/MLXFastModel/LagunaRuntimeModel.swift"

# sha256 of $TARGET for each arm, so a silently mis-applied patch cannot be
# timed as if it were the arm it claims to be.
sha_for_arm() {
  case "$1" in
    T0)  echo a736b50f66b08b9004a807ff38226aaeb95ba836e6e833b51a8e862466d850c4 ;;
    T1)  echo 2110d7bae3a62a72b5069cdee0f7b6e5fb78399059ac94adacc9a519281c7df5 ;;
    T0P) echo 9c2263730192bee13687d2a34198972807ab4b9ca1970e7610606eadf9758944 ;;
    T1P) echo 7a6aca9e9bec0c03adbb952a0d67b5ed5600b323aee6f300c572fefc65c6fad1 ;;
    T0U) echo ebebe3faad9f232f4bb94a62719a80f4cc7d10d47cff8aee09acce0036d57735 ;;
    *)   echo "unknown" ;;
  esac
}

base_for_arm() {
  case "$1" in
    T0|T0P|T0U) echo "$T0_SHA" ;;
    T1|T1P)     echo "$T1_SHA" ;;
    *)          echo "" ;;
  esac
}

armA="${1:?armA}"
armB="${2:?armB}"
blocks="${3:-3}"
restore_arm="${4:-T1}"
tag="${5:-$(echo "${armA}_${armB}" | tr 'A-Z' 'a-z')}"

root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$root" || exit 3
patch_file="$root/research/tanjiro_packing_default_flip.patch"
u_patch_file="$root/research/r106j/t0u_unroll_depth.patch"
art="$root/research/artifacts/maple-fern-r106j/abba_${tag}"
mkdir -p "$art"
tsv="$art/runs.tsv"
[ -f "$tsv" ] || printf 'idx\tarm\tstarted_utc\twall_s\trc\tdecode_s_per_token\tprefill_s_per_token\tpassed\tmax_abs_diff\tgolden_hash\tworker_sha256\n' > "$tsv"

select_arm() {
  local arm="$1" base want got n
  base="$(base_for_arm "$arm")"
  [ -n "$base" ] || { echo "[abba] FATAL: unknown arm $arm" >&2; return 8; }
  rm -rf "${PATHS[@]}" || return 4
  git checkout "$base" -- "${PATHS[@]}" || return 5
  n=$(git diff --numstat "$base" -- "${PATHS[@]}" | wc -l | tr -d ' ')
  [ "$n" = "0" ] || { echo "[abba] FATAL: $arm base $base not materialised ($n differ)" >&2; return 6; }
  case "$arm" in
    *P) git apply -p1 "$patch_file"   || { echo "[abba] FATAL: patch failed for $arm" >&2; return 9; } ;;
    *U) git apply -p1 "$u_patch_file" || { echo "[abba] FATAL: patch failed for $arm" >&2; return 9; } ;;
  esac
  want="$(sha_for_arm "$arm")"
  got="$(shasum -a 256 "$TARGET" | cut -d' ' -f1)"
  [ "$want" = "$got" ] || { echo "[abba] FATAL: $arm sha mismatch want=$want got=$got" >&2; return 7; }
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
    seq_arms+=("$armA" "$armB" "$armB" "$armA")
  else
    seq_arms+=("$armB" "$armA" "$armA" "$armB")
  fi
done

idx=$done_rows
for arm in "${seq_arms[@]}"; do
  idx=$((idx + 1))
  echo "[abba] run $idx arm=$arm"
  select_arm "$arm" || exit $?

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
$(python3 "$root/research/r106j/scripts/parse_iterate_json.py" "$art/run${idx}.${arm}.json")
EOF

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$idx" "$arm" "$started" "$wall" "$rc" "$dec" "$pre" "$passed" "$mad" "$gh" "$wsha" >> "$tsv"
  echo "[abba] run $idx arm=$arm rc=$rc decode=$dec prefill=$pre passed=$passed gh=$gh"
done

select_arm "$restore_arm" || exit 7
git checkout -- Package.resolved 2>/dev/null
# select_arm stages its checkout; without this the index re-adds paths the
# restored arm deletes and a later `git commit -a` would silently revive them.
git reset -q
echo "[abba] restored arm=$restore_arm"
column -t -s $'\t' "$tsv"
