#!/bin/bash
# Dispatch one R93 official submission.
#
#   submit_replicate.sh null <n>
#
# Rewrites the trailing marker comment on the scored file, renders the note,
# commits, and submits. The marker is what makes the editable surface distinct;
# the service deduplicates identical surfaces, so two replicates without
# distinct markers would collapse into one receipt.
set -u

KIND="$1"
VALUE="$2"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
case "$KIND" in
  null)   MARKER="senpai-r93-null-${VALUE}"; NOTE="research/r93-runs/note-null-${VALUE}.md" ;;
  ladder) MARKER="senpai-r93-ladder-K${VALUE}"; NOTE="research/r93-runs/note-ladder-K${VALUE}.md" ;;
  probe)  MARKER="senpai-r93-probe-routed-fma-${VALUE}"; NOTE="research/r93-runs/note-probe-routed-fma-${VALUE}.md" ;;
  *) echo "usage: submit_replicate.sh {null|ladder|probe} <value>"; exit 2 ;;
esac

# The marker always occupies the last line of the file.
python3 - "$SRC" "$MARKER" <<'PY'
import sys
path, marker = sys.argv[1], sys.argv[2]
lines = open(path).read().rstrip("\n").split("\n")
if lines and lines[-1].startswith("// senpai-r93-"):
    lines[-1] = "// " + marker
else:
    lines.append("")
    lines.append("// " + marker)
open(path, "w").write("\n".join(lines) + "\n")
PY
tail -2 "$SRC"

python3 research/r93-runs/make_note.py "$KIND" "$VALUE" \
  --prior research/r93-runs/prior.json || exit 1

git add -A -- "$SRC" research/r93-runs
git commit -q -m "r93 ${MARKER}: official receipt replicate" || echo "nothing to commit"
COMMIT="$(git rev-parse HEAD)"
echo "commit=${COMMIT}"

export PATH="${HOME}/.local/bin:${PATH}"
mlxfast submit --model "senpai" --note-file "$NOTE" 2>&1 | tee "/tmp/r93/submit-${MARKER}.log"
