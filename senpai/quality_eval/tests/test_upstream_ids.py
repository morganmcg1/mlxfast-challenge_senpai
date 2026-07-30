from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Callable

UPSTREAM = Path(__file__).resolve().parent.parent / "upstream"
sys.path.insert(0, str(UPSTREAM))

from aime_eval import filter_by_ids as filter_aime_by_ids
from gsm8k_eval import filter_by_ids as filter_gsm8k_by_ids


class IDFilterTests(unittest.TestCase):
    filters: tuple[
        tuple[str, Callable[[list[dict[str, Any]], list[Any]], list[dict[str, Any]]]],
        ...,
    ] = (
        ("AIME", filter_aime_by_ids),
        ("GSM8K", filter_gsm8k_by_ids),
    )

    def test_preserves_dataset_order_not_manifest_order(self) -> None:
        items = [{"id": "third"}, {"id": "first"}, {"id": "second"}]
        for name, filter_items in self.filters:
            with self.subTest(evaluator=name):
                selected = filter_items(items, ["second", "third"])
                self.assertEqual(
                    [item["id"] for item in selected],
                    ["third", "second"],
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


if __name__ == "__main__":
    unittest.main()
