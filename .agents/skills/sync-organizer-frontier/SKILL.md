---
name: sync-organizer-frontier
description: Safely update the mlxfast-challenge_senpai fork from Layr-Labs/mlxfast-challenge by cherry-picking reviewed organizer rule and contract commits, then importing the latest promoted editable-path solver snapshot without overwriting Senpai research files. Use when refreshing fork main, adopting new challenge rules or pinned dependencies, or moving the research base to a newer promoted frontier.
---

# Sync Organizer Frontier

Integrate in a dedicated branch. Keep organizer policy, the promoted solver
snapshot, and fork-only fixes as separate commits.

## Rules

- `origin` is the research fork; `upstream` is `Layr-Labs/mlxfast-challenge`.
- Never run either `mlxfast sync` mode on fork main or a research branch. Never
  pull or hard-reset the fork to `upstream/main`.
- Never push to `upstream`.
- Never cherry-pick bot `Validate submission` or `Accept submission` commits.
  They are deltas between unrelated solver trees, though one may be the source
  of the exact promoted snapshot.
- Get the promoted commit from `mlxfast submissions --all`, not the newest Git
  commit or a branch name.
- Preserve `senpai/`, especially `senpai/program.md`.

## Procedure

1. Require a clean tree, confirm remotes, and start from fork main:

```bash
git status --short
git remote -v
git fetch origin main
git fetch upstream main
git switch -c codex/sync-organizer-frontier origin/main
FORK_BASE_SHA="$(git rev-parse HEAD)"
SENPAI_TREE_SHA="$(git rev-parse HEAD:senpai)"
```

If needed, add `upstream` with the organizer URL. Use a fresh branch name.

2. Find policy candidates:

```bash
git log --reverse --no-merges --cherry-pick --right-only \
  --format='%H%x09%an%x09%s' "$FORK_BASE_SHA"...upstream/main
git show --stat <candidate-sha>
```

Select only organizer rules, contracts, enforcement, manifests, and pins. Skip
merge wrappers, bot commits, scores, and solver snapshots. Patch equivalence is
only a first filter; also skip policy already present after an earlier conflict
resolution. Cherry-pick selected commits oldest first with `git cherry-pick -x`.
Keep concise fork-owned guidance while adopting final organizer enforcement.

3. Identify and inspect the promoted solver:

```bash
mlxfast submissions --all
ORGANIZER_FRONTIER_SHA="paste-promoted-commit-sha"
git cat-file -e "$ORGANIZER_FRONTIER_SHA^{commit}"
git merge-base --is-ancestor "$ORGANIZER_FRONTIER_SHA" upstream/main
git show --stat --oneline "$ORGANIZER_FRONTIER_SHA"
```

Record its score. Do not substitute a newer validating or rejected submission.

4. Restore one exact editable snapshot using the current contract (zsh):

```zsh
editable_paths=(${(f)"$(jq -r '.editablePaths[]' benchmark.json)"})
git restore --source="$ORGANIZER_FRONTIER_SHA" --worktree -- $editable_paths
git diff --exit-code "$ORGANIZER_FRONTIER_SHA" -- $editable_paths
git add -- $editable_paths
git commit -m "Sync promoted organizer frontier"
```

Do not replay the frontier commit's diff. Reapply required fork compatibility
fixes separately and against the new code. The current known fix is the
M4/pre-NAX packed MoE layout guard; retain it only while necessary and adapt it
to the promoted layout stages.

5. Verify:

```zsh
test "$(git rev-parse HEAD:senpai)" = "$SENPAI_TREE_SHA"
git diff --name-only "$ORGANIZER_FRONTIER_SHA" -- $editable_paths
git diff --check
swift test --force-resolved-versions
git log --oneline "$FORK_BASE_SHA"..HEAD
```

The editable diff may contain only approved fork fixes. Confirm imported
contract/enforcement files match `upstream/main` where intended. Run
`tools/build-mlx-metallib.sh` whenever AOT Metal sources changed.
The full suite's
`staticReviewKernelPolicyAndLaunchBudgetCoverEnlargedSurface` test fails on the
combined base's total or per-file source cap and checks growth-cap enforcement.

6. After review, fast-forward fork main. If main moved, stop and re-integrate:

```bash
INTEGRATION_SHA="$(git rev-parse HEAD)"
git fetch origin main
test "$(git rev-parse origin/main)" = "$FORK_BASE_SHA"
git switch main
git merge --ff-only "$INTEGRATION_SHA"
BASE_SHA="$(git rev-parse HEAD)"
```

Report `ORGANIZER_FRONTIER_SHA`, `BASE_SHA`, imported policy commits, remaining
fork-only editable deltas, and checks run. Push only when asked.
