#!/usr/bin/env bash
# Publish the R109-F maple-fern campaign to W&B.
#
# `wandb/` is not in .gitignore and a dirty worktree blocks both `run_job` and
# `senpai/submit-official.sh`, so keep every W&B artifact out of the checkout.
set -uo pipefail

export WANDB_DIR="${WANDB_DIR:-/tmp/fern_wandb}"
export WANDB_CACHE_DIR="${WANDB_CACHE_DIR:-/tmp/fern_wandb/cache}"
export WANDB_CONFIG_DIR="${WANDB_CONFIG_DIR:-/tmp/fern_wandb/config}"
export WANDB_ARTIFACT_DIR="${WANDB_ARTIFACT_DIR:-/tmp/fern_wandb/artifacts}"
export WANDB_SILENT="${WANDB_SILENT:-false}"
mkdir -p "$WANDB_DIR" "$WANDB_CACHE_DIR" "$WANDB_CONFIG_DIR" "$WANDB_ARTIFACT_DIR"

cd "$(dirname "$0")/.."
echo "WANDB_DIR=$WANDB_DIR"
echo "HEAD=$(git rev-parse HEAD)"
exec python3 research/fern_r109f_wandb_campaign.py "$@"
