#!/usr/bin/env bash
# R107-J: thin wrapper that publishes the certification-instrument run to W&B.
#
# Its only job is to keep wandb's run directory OUT of the repository checkout.
# `wandb.init` writes ./wandb/ relative to the process cwd, the checkout has no
# .gitignore entry for it, and an untracked ./wandb/ tree would leave the
# worktree dirty -- which would invalidate the "these numbers describe commit X"
# claim the report makes.  So: run from /tmp, with WANDB_DIR pinned there.
#
# Usage:
#   research/maple-nezuko-r107j-wandb-run.sh <aa-null.tsv> [<extra.tsv> ...]
# Defaults to /tmp/r107j-aa-null.tsv when no argument is given.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
export WANDB_DIR="${WANDB_DIR:-/tmp/r107j-wandb}"
mkdir -p "${WANDB_DIR}"

if [[ $# -eq 0 ]]; then
  set -- /tmp/r107j-aa-null.tsv
fi

for f in "$@"; do
  if [[ ! -s "$f" ]]; then
    echo "FATAL: missing or empty table: $f" >&2
    exit 2
  fi
  # Rule 86 guard: --local-iterate output must never reach W&B as evidence.
  if grep -qi 'local-iterate' "$f"; then
    echo "FATAL: $f mentions local-iterate; refusing to publish (rule 86)" >&2
    exit 2
  fi
done

cd /tmp

echo "repo:      ${REPO}"
echo "WANDB_DIR: ${WANDB_DIR}"
echo "mode:      ${WANDB_MODE:-online}"
echo "tables:    $*"
echo

exec python3 "${REPO}/research/maple-nezuko-r107j-wandb-log.py" "$@"
