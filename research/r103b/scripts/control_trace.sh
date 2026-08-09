#!/bin/bash
# Control: run correctness-trace with the UNINSTRUMENTED worker from the main worktree.
set -u
ROOT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-tanjiro/workspace/target"
DUMP=/tmp/r103b/dump/control
rm -rf "$DUMP"; mkdir -p "$DUMP"
REAL="${ROOT}/.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker"
WRAP="${DUMP}/worker-wrap.sh"
cat > "$WRAP" <<EOF
#!/bin/bash
exec "${REAL}" "\$@" 2>> "${DUMP}/worker_stderr.log"
EOF
chmod +x "$WRAP"
cd "$ROOT" || exit 3
env -i HOME="${HOME:-/Users/ec2-user}" PATH="${PATH}" TMPDIR="${TMPDIR:-/tmp}" \
  USER="${USER:-ec2-user}" LOGNAME="${LOGNAME:-ec2-user}" SHELL=/bin/bash TERM=dumb \
  MLXFAST_NO_SANDBOX=1 \
  MLXFAST_RUNTIME_WORKER_EXECUTABLE="${WRAP}" \
  "${ROOT}/.build/release/mlxfast-swift" correctness-trace \
    --weights "${ROOT}/weights" \
    --golden "${ROOT}/correctness_prompts/public_longcopy_gate_english_512_256.json" \
    --step 5 --top-k 5 \
  > "${DUMP}/trace_report.json" 2> "${DUMP}/cli_stderr.log"
echo "control rc=$?"
echo "--- cli_stderr ---"; tail -n 20 "${DUMP}/cli_stderr.log"
echo "--- worker_stderr ---"; tail -n 40 "${DUMP}/worker_stderr.log"
echo "--- report head ---"; head -c 600 "${DUMP}/trace_report.json"
echo
echo CONTROLDONE
