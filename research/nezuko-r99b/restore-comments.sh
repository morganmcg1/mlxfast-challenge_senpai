#!/usr/bin/env bash
# Reapply the prose removed by rung 1 of maple-r99-b-comment-byte-reclamation.
#
# The strip is a pure deletion of comment content from 26 vendored editable
# files, so reverse-applying the recorded patch restores every byte exactly.
# Nothing under mlx-generated/ is in scope, and no AOT source whose body is
# snapshotted into an mlx-generated twin is touched: those sources are
# deliberately left byte-identical to base (see embedded-twin-exclusions.txt).
# git apply refuses a partial application, so a conflict fails loudly instead
# of leaving a half-restored tree.
#
#   research/nezuko-r99b/restore-comments.sh [--check]
#
# --check reports whether the restore would apply cleanly without writing.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." >/dev/null && pwd -P)"
PATCH="${ROOT_DIR}/research/nezuko-r99b/rung1-comment-strip.patch"
BASE_SHA="ad39bfc6c36c0a8257ee0de1916edafdbf52278e"

cd "${ROOT_DIR}"
[[ -f "${PATCH}" ]] || { echo "missing patch: ${PATCH}" >&2; exit 1; }

if [[ "${1:-}" == "--check" ]]; then
  git apply --reverse --check "${PATCH}"
  echo "restore would apply cleanly"
  exit 0
fi

git apply --reverse "${PATCH}"
echo "restored comment content from ${PATCH}"

# Independent confirmation that the restore is byte-exact, not merely clean.
remaining="$(git diff --name-only "${BASE_SHA}" -- Vendor/)"
if [[ -z "${remaining}" ]]; then
  echo "verified: vendored tree is byte-identical to ${BASE_SHA}"
else
  echo "WARNING: still differs from ${BASE_SHA}:" >&2
  printf '%s\n' "${remaining}" >&2
  exit 1
fi
