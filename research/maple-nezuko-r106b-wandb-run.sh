#!/usr/bin/env bash
# R106-B: thin wrapper that publishes the Stage B evidence to W&B.
#
# Its only job is to keep wandb's run directory OUT of the repository checkout:
# `wandb.init` writes ./wandb/ relative to the process cwd, the checkout has no
# .gitignore entry for it, and an untracked ./wandb/ tree would leave the
# worktree dirty -- which in turn invalidates the "these checks describe commit
# X" claim in research/maple-nezuko-r106b-verify-handoff.sh.  So: run from /tmp,
# with WANDB_DIR pinned there too.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
export WANDB_DIR="${WANDB_DIR:-/tmp/r106b-wandb}"
mkdir -p "${WANDB_DIR}"
cd /tmp

echo "repo:      ${REPO}"
echo "WANDB_DIR: ${WANDB_DIR}"
echo "mode:      ${WANDB_MODE:-online}"
echo

exec python3 "${REPO}/research/maple-nezuko-r106b-wandb-log.py" \
  /tmp/r106b-packred-evidence.tsv \
  /tmp/r106b-packred-triage.tsv \
  /tmp/r106b-h4-triage-d4.tsv
