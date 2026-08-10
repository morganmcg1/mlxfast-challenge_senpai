#!/bin/bash
# Build the public submission note for one r105-A ladder receipt.
# usage: research/r105a-make-note.sh ARM "one-line arm description"
set -u
ARM="$1"; DESC="$2"
OUT="research/r105a-notes/${ARM}.md"
mkdir -p research/r105a-notes
{
  printf '# r105-A ladder receipt %s\n\n' "$ARM"
  printf '**Arm:** `%s` - %s\n\n' "$ARM" "$DESC"
  printf 'This receipt is one rung of a preregistered ladder (order `A0-1, A0-2, A2-1,\n'
  printf 'A1-1, A0-3, A1-2, A2-2, spare`, minimum four receipts, cap eight). The `A0`\n'
  printf 'rungs are the null control: the identical tree with the compiled-in\n'
  printf 'tile-selection default unchanged, submitted more than once so the run-to-run\n'
  printf 'spread of the ranked instrument is measured rather than assumed. Only an inert\n'
  printf 'receipt-marker comment distinguishes replicate archives, because the service\n'
  printf 'deduplicates byte-identical submissions.\n\n'
  printf 'The shared methodology, arithmetic, self-refutation, and reproduction commands\n'
  printf 'for every rung follow.\n\n---\n\n'
  cat research/tanjiro-r105a-note-common.md
} > "$OUT"
wc -c "$OUT"
