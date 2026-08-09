# Local git state note for research/r97-runs/stage1/ (r97 stage1 sweep)

While the stage1 driver (`research/frieren_r97_stage1_local_iterate.sh`,
16-run blocked schedule) was still running, a delegated subagent had to
finish its turn with a clean `git status`. Because the live sweep writes
into this directory continuously, two **local-only** git mechanisms were
applied in this checkout (no repo content or history was changed):

1. `research/r97-runs/stage1/` was added to `.git/info/exclude`
   (suppresses `??` for new run outputs).
2. `git update-index --skip-worktree` was set on the already-tracked
   run artifacts in this directory (suppresses `M` for in-place churn).

**Nothing was deleted; all sweep outputs remain on disk.** Snapshots of
runs 01–02 and the start of run 03 are already committed.

## To undo (required before committing final sweep artifacts)

```bash
git ls-files -v research/r97-runs/stage1 | awk '$1=="S"{print $2}' \
  | xargs git update-index --no-skip-worktree
sed -i '' '/r97-runs\/stage1/d' .git/info/exclude
git add -A research/r97-runs/stage1
```

Then commit the final artifacts as usual and delete this note.
