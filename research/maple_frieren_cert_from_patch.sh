#!/bin/bash
# ONE COMMAND: a requester's diff -> a margin-certificate verdict.
#
#   bash research/maple_frieren_cert_from_patch.sh \
#       --patch /tmp/tanjiro-splitk.diff \
#       --base  2454cc01ea3afabac067f0a271e36901fea7d21c \
#       --out   research/artifacts/maple-frieren-r107f/sop/cert_splitk.json
#
# WHY IT EXISTS.  The margin-certificate service
# (research/maple-frieren-margin-certificate-service.md) asks a requester for a
# diff and a base sha, and nothing else.  Everything between those two inputs
# and a verdict is mechanical, and every manual step in it is a chance to
# produce a certificate of the wrong thing.  The failure that motivated this
# script is specific: if the candidate is not actually rebuilt, the logits are
# bitwise identical and a naive comparison reports PASS-BIT-EXACT -- the
# strongest verdict -- for a change that never ran.  (PR #575 hit the same
# class of error in the equivalence oracle.)
#
# THE GUARANTEE THIS SCRIPT MAKES.  Both arms are force-clean-built from ONE
# scratch worktree at the SAME base commit, so the trees are provably identical
# up to the requester's patch; and the candidate's worker/metallib fingerprints
# are checked to have MOVED before the candidate arm is captured.  A certificate
# from this script cannot be a certificate of a forgotten rebuild.
#
# WHAT IT DOES NOT DO.  It does not decide whether to ship.  Read
# 6_what_this_does_NOT_cover in the JSON: one prompt, 65 positions, no GPQA, no
# TTFT, no hidden-anchor coverage.  A PASS is "no token moved HERE, with this
# much margin to spare", not "correct".
#
# EXIT CODES (the instrument's, so `cert && ship` is safe):
#   0 PASS-BIT-EXACT or PASS-WITH-MARGIN     3 VOID -- says nothing, never ship
#   4 FAIL -- token flip / free-run divergence
#   5 MARGINAL -- under 10x safety, a human must read the report
#   1 usage error                            2 build or capture failure
set -uo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
SCRIPT="$REPO/research/maple-frieren-r106j-margin-certificate.py"
RESOURCES="mlx.metallib mlx.metallib.fingerprint mlx-swift-lm_MLXLMCommon.bundle swift-crypto_Crypto.bundle swift-transformers_Hub.bundle"

PATCH=""
BASE=""
OUT=""
MODE=teacher
STEPS=64
WT=/tmp/cert-from-patch
KEEP=0
# A space-separated K=V string, not an array: /bin/bash here is 3.2, where
# expanding an empty array under `set -u` is itself an error.
CAND_ENV=""

usage() {
  sed -n '2,30p' "$0"
  cat <<'EOF'

OPTIONS
  --patch FILE        unified diff to apply to the base tree (required unless
                      --candidate-env is given: an env-only mechanism probe)
  --base SHA          base commit both arms are built from (default: HEAD)
  --out FILE          certificate JSON (default: /tmp/cert-from-patch/cert.json)
  --mode teacher|free teacher-forced (what the official gate does) or greedy
                      self-feed (emulates the hidden free_run gate). Run BOTH
                      for anything that ships; teacher agreement does not imply
                      free-run agreement.
  --steps N           gate positions after step 0 (default 64, the gate's own)
  --scratch DIR       scratch worktree path (default /tmp/cert-from-patch)
  --candidate-env K=V repeatable. Sets an env var for the CANDIDATE arm only.
                      With no --patch this becomes an env-only arm: valid as a
                      mechanism probe, but the official harness does not set our
                      environment, so it certifies NOTHING that ships.
  --keep              do not remove the scratch worktree (for follow-up runs)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --patch) PATCH="$2"; shift 2 ;;
    --base) BASE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --steps) STEPS="$2"; shift 2 ;;
    --scratch) WT="$2"; shift 2 ;;
    --candidate-env) CAND_ENV="$CAND_ENV $2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option $1" >&2; usage >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------- preflight
if [ -z "$PATCH" ] && [ -z "$CAND_ENV" ]; then
  echo "FATAL: need --patch (a real candidate) or --candidate-env (a probe)" >&2
  usage >&2; exit 1
fi
if [ -n "$PATCH" ] && [ ! -f "$PATCH" ]; then
  echo "FATAL: no such patch file: $PATCH" >&2; exit 1
fi
[ -n "$PATCH" ] && PATCH=$(cd "$(dirname "$PATCH")" && pwd)/$(basename "$PATCH")
BASE=${BASE:-$(git -C "$REPO" rev-parse HEAD)}
BASE_FULL=$(git -C "$REPO" rev-parse --verify "$BASE^{commit}" 2>/dev/null) || {
  echo "FATAL: base commit '$BASE' is not in this repository. Fetch it first." >&2
  exit 1; }
OUT=${OUT:-$WT/cert.json}
mkdir -p "$(dirname "$OUT")"
[ -x "$REPO/weights" ] || [ -d "$REPO/weights" ] || {
  echo "FATAL: no weights/ in $REPO; the worker cannot load the model." >&2
  exit 1; }

sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
PATCH_SHA=none
[ -n "$PATCH" ] && PATCH_SHA=$(sha "$PATCH")
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

echo "=============================================================="
echo "cert-from-patch   $STAMP"
echo "  repo        $REPO"
echo "  base        $BASE_FULL"
echo "  patch       ${PATCH:-<none>}"
echo "  patch sha   $PATCH_SHA"
echo "  cand env   ${CAND_ENV:-  <none>}"
echo "  mode/steps  $MODE / $STEPS"
echo "  out         $OUT"
echo "=============================================================="

build() {  # force-clean-ish build in $1; metallib is NOT in swift's dep graph
  local dir="$1"
  ( cd "$dir" \
    && mkdir -p .build-worker/clang-module-cache \
    && CLANG_MODULE_CACHE_PATH="$dir/.build-worker/clang-module-cache" \
       swift build -c release --force-resolved-versions \
         --scratch-path .build-worker --product mlxfast-runtime-worker ) \
  && ( cd "$dir" && bash tools/build-mlx-metallib.sh >/dev/null ) \
  && ( cd "$dir" && git checkout -- Package.resolved 2>/dev/null; true )
}

T0=$(date +%s)

# ------------------------------------------------------- phase 1: worktree
echo "### phase 1/6  scratch worktree at $BASE_FULL"
if [ -d "$WT/.git" ] || [ -f "$WT/.git" ]; then
  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"
fi
rm -rf "$WT"
git -C "$REPO" worktree prune
git -C "$REPO" worktree add --detach "$WT" "$BASE_FULL" || {
  echo "FATAL: worktree add failed" >&2; exit 2; }
HAVE=$(git -C "$WT" rev-parse HEAD)
[ "$HAVE" = "$BASE_FULL" ] || {
  echo "FATAL: worktree is at $HAVE, not $BASE_FULL" >&2; exit 2; }
T1=$(date +%s)

# ---------------------------------------------------- phase 2: build base
echo "### phase 2/6  build BASELINE arm (worker + metallib, force-clean)"
build "$WT" || { echo "FATAL: baseline build failed" >&2; exit 2; }
BW="$WT/.build-worker/release/mlxfast-runtime-worker"
BASE_WSHA=$(sha "$BW"); BASE_MSHA=$(sha "$WT/.build-worker/release/mlx.metallib")
for f in $RESOURCES; do
  [ -e "$WT/.build-worker/release/$f" ] || echo "WARNING: missing resource $f" >&2
done
echo "  baseline worker   $BASE_WSHA"
echo "  baseline metallib $BASE_MSHA"
T2=$(date +%s)

# -------------------------------------------------- phase 3: capture base
echo "### phase 3/6  capture BASELINE arm"
python3 "$SCRIPT" capture --worker "$BW" --mode "$MODE" --steps "$STEPS" \
  --label "base@${BASE_FULL:0:12}" --out "$WT/baseline.npz" || {
  echo "FATAL: baseline capture failed (see $WT/baseline.worker.err)" >&2
  exit 2; }
T3=$(date +%s)

# ------------------------------------- phase 4: apply patch, rebuild, check
if [ -n "$PATCH" ]; then
  echo "### phase 4/6  apply patch and rebuild CANDIDATE arm"
  git -C "$WT" apply --whitespace=nowarn "$PATCH" || {
    echo "FATAL: patch does not apply to $BASE_FULL. The requester's base sha" >&2
    echo "       and their diff disagree; ask for both again." >&2
    exit 2; }
  git -C "$WT" --no-pager diff --stat | sed 's/^/  /'
  build "$WT" || { echo "FATAL: candidate build failed" >&2; exit 2; }
  CAND_WSHA=$(sha "$BW"); CAND_MSHA=$(sha "$WT/.build-worker/release/mlx.metallib")
  echo "  candidate worker   $CAND_WSHA"
  echo "  candidate metallib $CAND_MSHA"
  if [ "$CAND_WSHA" = "$BASE_WSHA" ] && [ "$CAND_MSHA" = "$BASE_MSHA" ]; then
    echo "FATAL: the patch applied but NEITHER the worker nor mlx.metallib" >&2
    echo "       changed. Either the diff is a no-op for the compiler (only" >&2
    echo "       comments/whitespace), or it touches code this product does" >&2
    echo "       not link. Certifying now would report PASS-BIT-EXACT for a" >&2
    echo "       change that cannot run: refusing." >&2
    exit 3
  fi
else
  echo "### phase 4/6  no patch: env-only arm, reusing the baseline build"
  CAND_WSHA=$BASE_WSHA; CAND_MSHA=$BASE_MSHA
fi
T4=$(date +%s)

# --------------------------------------------- phase 5: capture candidate
echo "### phase 5/6  capture CANDIDATE arm"
CLABEL="cand@${BASE_FULL:0:12}+patch${PATCH_SHA:0:8}"
[ -n "$CAND_ENV" ] && CLABEL="$CLABEL+env"
# $CAND_ENV is deliberately unquoted: it is a K=V word list for `env`.
env $CAND_ENV python3 "$SCRIPT" capture --worker "$BW" --mode "$MODE" \
  --steps "$STEPS" --label "$CLABEL" --out "$WT/candidate.npz" || {
  echo "FATAL: candidate capture failed (see $WT/candidate.worker.err)." >&2
  echo "       A worker that will not start IS a result: report it as such." >&2
  exit 2; }
T5=$(date +%s)

# -------------------------------------------------------- phase 6: certify
echo "### phase 6/6  certify"
python3 "$SCRIPT" certify --baseline "$WT/baseline.npz" \
  --candidate "$WT/candidate.npz" --out "$OUT"
RC=$?
T6=$(date +%s)

echo
echo "=============== timing (seconds, wall) ==============="
printf '  worktree %5d\n  build base %5d\n  capture base %5d\n' \
  $((T1-T0)) $((T2-T1)) $((T3-T2))
printf '  patch+rebuild %5d\n  capture cand %5d\n  certify %5d\n  TOTAL %5d\n' \
  $((T4-T3)) $((T5-T4)) $((T6-T5)) $((T6-T0))
echo "======================================================"
echo "certificate: $OUT"
echo "exit code:   $RC  (0 pass / 3 void / 4 fail / 5 marginal)"
echo "provenance:  base $BASE_FULL  patch-sha256 $PATCH_SHA"
echo "  baseline worker/metallib $BASE_WSHA / $BASE_MSHA"
echo "  candidate worker/metallib $CAND_WSHA / $CAND_MSHA"
if [ -n "$PATCH" ]; then
  echo "NOTE: the candidate arm is base+patch in a WORKING TREE, so the"
  echo "      certificate carries a DIRTY BUILD TREE caveat by construction."
  echo "      Its reproducibility handle is the pair (base sha, patch sha256)"
  echo "      printed above, not a single commit."
fi
if [ "$KEEP" -eq 0 ]; then
  cp "$WT/baseline.worker.err" "$(dirname "$OUT")/baseline.worker.err" 2>/dev/null
  cp "$WT/candidate.worker.err" "$(dirname "$OUT")/candidate.worker.err" 2>/dev/null
  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"
else
  echo "kept scratch worktree: $WT"
fi
exit $RC
