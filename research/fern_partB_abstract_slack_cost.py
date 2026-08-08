"""What it would cost to stop cutting relocatable abstracts mid-sentence.

`keep_count` runs to the first sentence end but falls back to
ABSTRACT_HARD_LINES when a block's opening sentence is longer than that, which
leaves a truncated abstract at the declaration. This prices the alternative:
for every planned block cut mid-sentence, how many bytes the abstract would
have to keep to reach the next sentence end within a 1- and 5-line slack.

Run from the repository root: python3 research/fern_partB_abstract_slack_cost.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "research")
from frieren_comment_blocks import blocks
from fern_vendor_relocate_plan import (
    ABSTRACT_HARD_LINES, SENTENCE_END, hard_keep, keep_count, nbytes,
)

bl, lines = blocks(Path("Sources/MLXFastModel/LagunaRuntimeModel.swift"))
spec = json.load(open("research/fern_partB_lagunaruntimemodel_spec.json"))
planned = {(b["start"], b["end"]) for b in spec["files"][0]["blocks"]}

mid = 0
cost = {1: 0, 5: 0}
for start, end, body, unsafe in bl:
    if hard_keep(body, lines, end):
        continue
    k = keep_count(body)
    if (start + k, end) not in planned:
        continue
    if k and not SENTENCE_END.search(body[k - 1]):
        mid += 1
        for slack in (1, 5):
            for j in range(k, min(k + slack, len(body))):
                cost[slack] += nbytes(body[j])
                if SENTENCE_END.search(body[j]):
                    break

print("planned blocks:", len(planned))
print(f"mid-sentence cuts at ABSTRACT_HARD_LINES={ABSTRACT_HARD_LINES}:", mid)
print("byte cost to finish the sentence, slack=1:", cost[1])
print("byte cost to finish the sentence, slack=5:", cost[5])
print("comment pool all-in (blocks + literal-interior):", 120254 + 372)
