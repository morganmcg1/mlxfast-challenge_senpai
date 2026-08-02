from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .tokenizer import LagunaTokenizer


# The Gemma challenge's frozen PPL manifest contains Gemma token IDs (many
# above Laguna's 100,352-token vocabulary) and cannot be replayed against
# Laguna. These short, original continuations provide a deterministic local
# distribution-drift panel while retaining the official endpoint scorer and
# its token-weighted perplexity equation.
PPL_TEXT_RECORDS: tuple[dict[str, Any], ...] = (
    {
        "id": "science-explanation",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Explain why the sky is usually blue during the day and often "
                    "red near sunset. Keep the explanation precise."
                ),
            }
        ],
        "target": (
            "Sunlight contains many wavelengths. Air molecules scatter shorter "
            "blue wavelengths more strongly than red wavelengths, so diffuse blue "
            "light reaches us from across the daytime sky. Near sunset the direct "
            "light travels through more atmosphere, scattering much of the blue "
            "away and leaving warmer red and orange wavelengths."
        ),
    },
    {
        "id": "arithmetic-reasoning",
        "messages": [
            {
                "role": "user",
                "content": (
                    "A shop discounts an 80 euro item by 15%, then adds 23% VAT "
                    "to the discounted price. Show the calculation and final price."
                ),
            }
        ],
        "target": (
            "The discount is 0.15 × 80 = 12 euros, so the discounted price is "
            "68 euros. VAT is 0.23 × 68 = 15.64 euros. The final price is "
            "68 + 15.64 = 83.64 euros."
        ),
    },
    {
        "id": "python-debugging",
        "messages": [
            {
                "role": "user",
                "content": (
                    "In Python, why is `items = [[]] * 3` usually a bug when I "
                    "intend to create three independent lists?"
                ),
            }
        ],
        "target": (
            "List multiplication repeats references to the same inner list; it "
            "does not construct three independent lists. Mutating one element "
            "therefore appears to mutate all three. Use a comprehension such as "
            "`items = [[] for _ in range(3)]` to create distinct list objects."
        ),
    },
    {
        "id": "instruction-following",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Give exactly three concise reasons to write tests for a data "
                    "migration. Number them and do not add an introduction."
                ),
            }
        ],
        "target": (
            "1. Detect incorrect field mappings before production rollout.\n"
            "2. Verify that row counts and invariants survive the migration.\n"
            "3. Make rollback and repeat runs safer when inputs change."
        ),
    },
    {
        "id": "historical-summary",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Summarize the purpose of the printing press in early modern "
                    "Europe without claiming it was the first printing technology."
                ),
            }
        ],
        "target": (
            "Movable-type presses made European book production faster and cheaper "
            "than manuscript copying, allowing texts to circulate at much larger "
            "scale. They supported wider literacy, scholarship, religious debate, "
            "and administrative standardization, while building on earlier forms "
            "of printing developed elsewhere."
        ),
    },
    {
        "id": "safe-medical-guidance",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Someone has sudden chest pressure, sweating, and shortness of "
                    "breath. What should they do?"
                ),
            }
        ],
        "target": (
            "Treat this as a medical emergency. Call the local emergency service "
            "now, avoid driving yourself, and follow the dispatcher's instructions. "
            "Do not wait for the symptoms to pass or rely on an online diagnosis."
        ),
    },
    {
        "id": "compare-concepts",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Briefly distinguish correlation from causation and give one "
                    "reason a correlation can be misleading."
                ),
            }
        ],
        "target": (
            "Correlation means two measurements vary together; causation means a "
            "change in one helps produce a change in the other. A correlation can "
            "be misleading when a third variable influences both measurements, "
            "creating an association without a direct causal link."
        ),
    },
    {
        "id": "structured-writing",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Write a two-sentence release note for a command-line tool that "
                    "now saves JSON results and returns a nonzero status on failure."
                ),
            }
        ],
        "target": (
            "The CLI now writes each run's results to a structured JSON artifact "
            "for later inspection and comparison. Failed evaluations also return "
            "a nonzero exit status, making automation errors visible immediately."
        ),
    },
)


def build_manifest(
    tokenizer: LagunaTokenizer,
    output_path: Path,
    *,
    limit: int | None = None,
    max_target_tokens: int | None = None,
) -> dict[str, Any]:
    selected = PPL_TEXT_RECORDS[:limit] if limit is not None else PPL_TEXT_RECORDS
    records: list[dict[str, Any]] = []
    for source in selected:
        context = tokenizer.encode_messages(
            source["messages"],
            add_generation_prompt=True,
            enable_thinking=False,
        )
        target = tokenizer.encode_text(source["target"], add_special_tokens=False)
        if max_target_tokens is not None:
            target = target[:max_target_tokens]
        if not context or not target:
            raise ValueError(f"PPL record {source['id']} tokenized to an empty sequence")
        records.append(
            {
                "id": source["id"],
                "context_token_ids": context,
                "target_token_ids": target,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    output_path.write_text(payload)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    metadata = {
        "dataset": "laguna-quality-ppl-v1",
        "sha256": digest,
        "num_records": len(records),
        "num_context_tokens": sum(len(record["context_token_ids"]) for record in records),
        "num_target_tokens": sum(len(record["target_token_ids"]) for record in records),
        "tokenizer": str(tokenizer.directory),
        "manifest": str(output_path),
    }
    output_path.with_suffix(output_path.suffix + ".meta.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )
    return metadata
