from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

QUALITY_EVAL = Path(__file__).resolve().parent.parent
UPSTREAM = QUALITY_EVAL / "upstream"
MANIFESTS = QUALITY_EVAL / "manifests"
sys.path.insert(0, str(UPSTREAM))

from aime_eval import filter_by_ids as filter_aime_by_ids
from gsm8k_eval import (
    GSM8K_FEWSHOT_INDICES,
    build_fewshot,
    filter_by_ids as filter_gsm8k_by_ids,
)


class IDFilterTests(unittest.TestCase):
    filters: tuple[
        tuple[str, Callable[[list[dict[str, Any]], list[Any]], list[dict[str, Any]]]],
        ...,
    ] = (
        ("AIME", filter_aime_by_ids),
        ("GSM8K", filter_gsm8k_by_ids),
    )

    def test_preserves_manifest_order(self) -> None:
        items = [{"id": "third"}, {"id": "first"}, {"id": "second"}]
        for name, filter_items in self.filters:
            with self.subTest(evaluator=name):
                selected = filter_items(items, ["second", "third"])
                self.assertEqual(
                    [item["id"] for item in selected],
                    ["second", "third"],
                )

    def test_rejects_missing_requested_id(self) -> None:
        for name, filter_items in self.filters:
            with self.subTest(evaluator=name):
                with self.assertRaisesRegex(
                    ValueError,
                    "requested IDs not found: missing",
                ):
                    filter_items([{"id": "present"}], ["present", "missing"])

    def test_rejects_duplicate_requested_id(self) -> None:
        for name, filter_items in self.filters:
            with self.subTest(evaluator=name):
                with self.assertRaisesRegex(
                    ValueError,
                    "duplicate requested IDs: repeated",
                ):
                    filter_items([{"id": "repeated"}], ["repeated", "repeated"])

    def test_rejects_duplicate_selected_dataset_id(self) -> None:
        items = [{"id": "repeated"}, {"id": "repeated"}]
        for name, filter_items in self.filters:
            with self.subTest(evaluator=name):
                with self.assertRaisesRegex(
                    ValueError,
                    "duplicate dataset IDs: repeated",
                ):
                    filter_items(items, ["repeated"])


class QuickManifestTests(unittest.TestCase):
    def test_exact_quick_question_ids(self) -> None:
        self.assertEqual(
            json.loads((MANIFESTS / "quick_mmlu_pro.json").read_text()),
            [
                "10223",
                "10481",
                "12229",
                "2135",
                "238",
                "2762",
                "2974",
                "3180",
                "3293",
                "4405",
                "4559",
                "5032",
                "6198",
                "6274",
                "6993",
                "7267",
                "7323",
                "9252",
                "9398",
                "9462",
            ],
        )
        self.assertEqual(
            json.loads((MANIFESTS / "quick_gpqa_diamond.json").read_text()),
            [
                "rec06pnAkLOr2t2mp",
                "rec0Arme2jcXQZnAW",
                "rec0VuKUjt1SZ7NYv",
                "rec0wZvZgiz320KRs",
                "rec0yTRmO1o1xCA6H",
                "rec1oj2DveQWl9Rpw",
                "rec1zl5LvaatzGhFt",
                "rec260hNUCEj109Dj",
                "rec2UlKqC6RFHdcro",
            ],
        )
        self.assertEqual(
            json.loads((MANIFESTS / "quick_aime.json").read_text()),
            [
                "2024-2024-II-1",
                "2024-2024-II-2",
                "2024-2024-II-4",
                "2025-I-01",
                "2025-I-02",
                "2025-I-03",
                "2025-II-01",
                "2025-II-02",
                "2025-II-03",
            ],
        )
        self.assertEqual(
            json.loads((MANIFESTS / "quick_gsm8k.json").read_text()),
            [
                "test-774",
                "test-1165",
                "test-1216",
                "test-12",
                "test-122",
                "test-681",
            ],
        )

    def test_exact_quick_prompt_contract(self) -> None:
        self.assertEqual(
            json.loads((MANIFESTS / "quick_prompt_contract.json").read_text()),
            {
                "mmlu_pro_greedy": "bdb8bcda134409b68d24987bda6638bce4ec1136d2cba8d2997ffc390a2a8312",
                "gpqa_diamond_greedy": "cfd68df2948f20f01876ea097758bcc9b6251aa56fb3e5eccf13db67536618ac",
                "gpqa_diamond_sampled": "cfd68df2948f20f01876ea097758bcc9b6251aa56fb3e5eccf13db67536618ac",
                "gpqa_diamond_ranked_greedy": "cfd68df2948f20f01876ea097758bcc9b6251aa56fb3e5eccf13db67536618ac",
                "aime_greedy": "ea97a7f949fd89b10671420e47e3a6483892e8f8cdc51bbb1bf7a6f040748b39",
                "gsm8k_greedy": "703921f5f62ec25193606e883a504591e47ed3d69ac25fb2a7f0696181139c60",
            },
        )

    def test_gsm8k_fewshot_indices_are_frozen(self) -> None:
        expected = (52, 28, 38, 23, 12, 45, 26, 25)
        train = [
            {
                "question": f"question {index}",
                "answer": f"work {index} #### {index}",
            }
            for index in range(max(expected) + 1)
        ]

        with patch("gsm8k_eval._load_split", return_value=train):
            exemplars, signatures = build_fewshot(8, seed=1234)
            other_exemplars, other_signatures = build_fewshot(8, seed=9999)

        self.assertEqual(GSM8K_FEWSHOT_INDICES, expected)
        self.assertEqual(
            [exemplar["question"] for exemplar in exemplars],
            [f"question {index}" for index in expected],
        )
        self.assertEqual(
            [signature.split(":", 1)[0] for signature in signatures],
            [str(index) for index in expected],
        )
        self.assertEqual(other_exemplars, exemplars)
        self.assertEqual(other_signatures, signatures)


if __name__ == "__main__":
    unittest.main()
