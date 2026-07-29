from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

QUALITY_EVAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUALITY_EVAL))

from laguna_quality.ppl_manifest import build_manifest
from dataclasses import asdict

from laguna_quality.runner import (
    PROFILES,
    RANKED_GPQA_MAX_TOKENS,
    _pass_commands,
    compare_runs,
)
from upstream.aime_eval import _stratified_limit


HOST_IDENTITY = {
    "system": "Darwin",
    "system_release": "25.0.0",
    "machine": "arm64",
    "macos_version": "26.0",
    "hardware_model": "Mac16,7",
    "cpu_brand": "Apple M4 Max",
}
PUBLIC_PROBE = {
    "available": True,
    "fixture_sha256": "fixture",
    "prompt_token_count": 512,
    "expected_token": 5991,
    "actual_token": 8550,
    "matches_m5_fixture": False,
}


class FakeTokenizer:
    directory = Path("/fake/tokenizer")

    def encode_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        add_generation_prompt: bool,
        enable_thinking: bool,
    ) -> list[int]:
        assert add_generation_prompt and not enable_thinking
        return [2, len(messages[0]["content"])]

    def encode_text(self, text: str, *, add_special_tokens: bool) -> list[int]:
        assert not add_special_tokens
        return [ord(character) % 97 for character in text]


class PPLManifestTests(unittest.TestCase):
    def test_manifest_is_frozen_and_target_limited(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ppl.jsonl"
            metadata = build_manifest(
                FakeTokenizer(),
                path,
                limit=2,
                max_target_tokens=3,
            )
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(metadata["num_records"], 2)
            self.assertEqual(metadata["num_target_tokens"], 6)
            self.assertEqual(len(records[0]["target_token_ids"]), 3)
            self.assertEqual(
                metadata["sha256"],
                json.loads(path.with_suffix(".jsonl.meta.json").read_text())["sha256"],
            )


class RunnerCommandTests(unittest.TestCase):
    def test_smoke_profile_builds_every_suite(self) -> None:
        commands = _pass_commands(
            pass_number=2,
            pass_dir=Path("/tmp/run/pass_2"),
            suites=("ppl", "mmlu_pro", "gpqa_diamond", "aime", "gsm8k"),
            profile=PROFILES["smoke"],
            base_url="http://127.0.0.1:1234",
            ppl_dataset=Path("/tmp/ppl.jsonl"),
            ppl_records=2,
        )
        names = [name for name, _ in commands]
        self.assertEqual(
            names,
            [
                "ppl",
                "mmlu_pro_greedy",
                "gpqa_diamond_greedy",
                "gpqa_diamond_sampled_s1",
                "aime_greedy",
                "gsm8k_greedy",
            ],
        )
        sampled = dict(commands)["gpqa_diamond_sampled_s1"]
        self.assertIn("1", sampled)
        self.assertIn("--limit", sampled)

    def test_quick_profile_has_bounded_all_path_budget(self) -> None:
        profile = PROFILES["quick"]
        full_head_requests = (
            profile.mmlu_n
            + 2 * (profile.gpqa_limit or 0)
            + (profile.aime_limit or 0)
            + profile.gsm8k_n
        )
        ranked_head_requests = profile.gpqa_limit or 0
        ppl_tokens = 8 * (profile.ppl_target_tokens or 0)

        self.assertEqual(
            full_head_requests * profile.max_tokens
            + ranked_head_requests * RANKED_GPQA_MAX_TOKENS
            + ppl_tokens,
            14_976,
        )
        self.assertEqual(profile.max_connections, 1)
        self.assertEqual(profile.gpqa_limit, 9)

    def test_dual_head_phases_split_ranked_greedy_from_full_distribution(self) -> None:
        arguments = {
            "pass_number": 1,
            "pass_dir": Path("/tmp/run/pass_1"),
            "suites": ("ppl", "mmlu_pro", "gpqa_diamond", "aime", "gsm8k"),
            "profile": PROFILES["smoke"],
            "base_url": "http://127.0.0.1:1234",
            "ppl_dataset": Path("/tmp/ppl.jsonl"),
            "ppl_records": 2,
        }
        ranked = _pass_commands(**arguments, head_mode="ranked")
        full = _pass_commands(**arguments, head_mode="full")

        self.assertEqual(
            [name for name, _ in ranked],
            ["gpqa_diamond_ranked_greedy"],
        )
        self.assertEqual(
            [name for name, _ in full],
            [
                "ppl",
                "mmlu_pro_greedy",
                "gpqa_diamond_greedy",
                "gpqa_diamond_sampled_s0",
                "aime_greedy",
                "gsm8k_greedy",
            ],
        )
        for _, command in ranked:
            self.assertEqual(command[command.index("--min-tokens") + 1], "0")
            self.assertEqual(command[command.index("--max-tokens") + 1], "128")
            self.assertEqual(
                command[command.index("--prompt-format") + 1],
                "raw_single_user",
            )
        for _, command in full:
            self.assertNotIn("--prompt-format", command)


class LimitedDatasetTests(unittest.TestCase):
    def test_aime_limit_round_robins_across_requested_years(self) -> None:
        groups = [
            [{"id": "2024-1"}, {"id": "2024-2"}],
            [{"id": "2025-I-1"}, {"id": "2025-I-2"}],
            [{"id": "2025-II-1"}, {"id": "2025-II-2"}],
        ]
        self.assertEqual(
            [row["id"] for row in _stratified_limit(groups, 4)],
            ["2024-1", "2025-I-1", "2025-II-1", "2024-2"],
        )


class ComparisonTests(unittest.TestCase):
    def test_compare_reports_metrics_and_raw_response_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline"
            candidate = root / "candidate"
            for arm, accuracy, completion in (
                (baseline, 1.00, "A"),
                (candidate, 0.50, "B"),
            ):
                pass_dir = arm / "pass_1"
                pass_dir.mkdir(parents=True)
                rows = [
                    {
                        "id": "q1",
                        "prompt_sha": "prompt-1",
                        "completion": completion,
                        "correct": True,
                    },
                    {
                        "id": "q2",
                        "prompt_sha": "prompt-2",
                        "completion": completion,
                        "correct": accuracy == 1.0,
                    },
                ]
                pairs = sorted((row["id"], row["prompt_sha"]) for row in rows)
                dataset_sha = hashlib.sha256(
                    json.dumps(pairs, separators=(",", ":")).encode()
                ).hexdigest()
                contract = {
                    "status": "completed",
                    "evaluation_valid": True,
                    "profile": "smoke",
                    "profile_settings": asdict(PROFILES["smoke"]),
                    "passes": 1,
                    "suites": ["mmlu_pro"],
                    "head_modes": {
                        "full": {
                            "lm_head": "full_bf16",
                            "min_tokens": PROFILES["smoke"].min_tokens,
                            "max_tokens": PROFILES["smoke"].max_tokens,
                            "role": "quality_panel",
                        }
                    },
                    "prompt_formats": {
                        "mmlu_pro": {"full": "chat_template"},
                    },
                    "host_identity": HOST_IDENTITY,
                    "local_public_correctness_probe": PUBLIC_PROBE,
                    "evaluator_provenance": {"sha256": "same"},
                    "tokenizer_stop_token_ids": [2, 24],
                    "failures": [],
                    "artifact_identity": {
                        "files": {
                            "tokenizer/tokenizer.json": {"sha256": "tokenizer"},
                            "tokenizer/chat_template.jinja": {"sha256": "template"},
                        }
                    },
                }
                (arm / "run.json").write_text(json.dumps(contract))
                (arm / "summary.json").write_text(
                    json.dumps(
                        {
                            "arms": [
                                {
                                    "metrics": {
                                        "mmlu": {
                                            "mean": accuracy,
                                            "stdev": 0.0,
                                            "n": 1,
                                        }
                                    }
                                }
                            ]
                        }
                    )
                )
                (pass_dir / "mmlu_pro_greedy.json").write_text(
                    json.dumps(
                        {
                            "accuracy": accuracy,
                            "n_samples": 2,
                            "n_expected": 2,
                            "n_scored": 2,
                            "n_correct": int(accuracy * 2),
                            "n_error": 0,
                            "incomplete": False,
                            "dataset_sha256": dataset_sha,
                            "per_sample": rows,
                        }
                    )
                )

            comparison = compare_runs(baseline, candidate)

            self.assertEqual(comparison["metrics"]["mmlu"]["delta"], -0.50)
            self.assertEqual(comparison["response_identity"]["match_rate"], 0.0)
            self.assertEqual(comparison["response_identity"]["mismatches"][0]["id"], "q1")
            self.assertTrue(comparison["decision"]["baseline_regression"])
            self.assertEqual(comparison["decision"]["status"], "regression")
            self.assertIn("prompt_formats", comparison["compatibility"]["fields"])
            self.assertIn("host_identity", comparison["compatibility"]["fields"])
            self.assertTrue(
                comparison["response_identity"]["public_probe"]["matched"]
            )

            candidate_manifest = json.loads((candidate / "run.json").read_text())
            candidate_manifest["prompt_formats"]["mmlu_pro"]["full"] = (
                "raw_single_user"
            )
            (candidate / "run.json").write_text(json.dumps(candidate_manifest))
            with self.assertRaisesRegex(ValueError, "prompt-format policy"):
                compare_runs(baseline, candidate)

            candidate_manifest["prompt_formats"]["mmlu_pro"]["full"] = (
                "chat_template"
            )
            (candidate / "summary.json").write_text(
                (baseline / "summary.json").read_text()
            )
            (candidate / "pass_1" / "mmlu_pro_greedy.json").write_text(
                (baseline / "pass_1" / "mmlu_pro_greedy.json").read_text()
            )
            candidate_manifest["local_public_correctness_probe"]["actual_token"] = 42
            candidate_manifest["local_public_correctness_probe"][
                "matches_m5_fixture"
            ] = False
            (candidate / "run.json").write_text(json.dumps(candidate_manifest))
            probe_comparison = compare_runs(baseline, candidate)
            self.assertEqual(probe_comparison["decision"]["metric_regressions"], [])
            self.assertEqual(probe_comparison["response_identity"]["mismatches"], [])
            self.assertFalse(
                probe_comparison["response_identity"]["public_probe"]["matched"]
            )
            self.assertTrue(probe_comparison["decision"]["baseline_regression"])

            candidate_manifest["local_public_correctness_probe"]["actual_token"] = 8550
            candidate_manifest["host_identity"]["hardware_model"] = "Mac15,1"
            (candidate / "run.json").write_text(json.dumps(candidate_manifest))
            with self.assertRaisesRegex(ValueError, "host_identity"):
                compare_runs(baseline, candidate)

            candidate_manifest["host_identity"]["hardware_model"] = "Mac16,7"
            candidate_manifest["artifact_identity"]["files"][
                "tokenizer/tokenizer.json"
            ]["sha256"] = "different"
            (candidate / "run.json").write_text(json.dumps(candidate_manifest))
            with self.assertRaisesRegex(ValueError, "tokenizer_sha256s"):
                compare_runs(baseline, candidate)

    def test_compare_rejects_completed_run_with_missing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline"
            candidate = Path(temporary) / "candidate"
            contract = {
                "status": "completed",
                "evaluation_valid": True,
                "profile": "smoke",
                "profile_settings": asdict(PROFILES["smoke"]),
                "passes": 1,
                "suites": ["ppl"],
                "head_modes": {
                    "full": {
                        "lm_head": "full_bf16",
                        "min_tokens": PROFILES["smoke"].min_tokens,
                        "max_tokens": PROFILES["smoke"].max_tokens,
                        "role": "quality_panel",
                    }
                },
                "prompt_formats": {"ppl": {"full": "token_ids"}},
                "host_identity": HOST_IDENTITY,
                "local_public_correctness_probe": PUBLIC_PROBE,
                "ppl_manifest": {"sha256": "same", "num_records": 2},
                "evaluator_provenance": {"sha256": "same"},
                "tokenizer_stop_token_ids": [2, 24],
                "failures": [],
                "artifact_identity": {
                    "files": {
                        "tokenizer/tokenizer.json": {"sha256": "tokenizer"},
                        "tokenizer/chat_template.jinja": {"sha256": "template"},
                    }
                },
            }
            for arm in (baseline, candidate):
                arm.mkdir()
                (arm / "run.json").write_text(json.dumps(contract))
                (arm / "summary.json").write_text(json.dumps({"arms": []}))
            with self.assertRaisesRegex(ValueError, "missing"):
                compare_runs(baseline, candidate)

    def test_compare_rejects_missing_or_failed_run_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline"
            candidate = Path(temporary) / "candidate"
            baseline.mkdir()
            candidate.mkdir()
            with self.assertRaisesRegex(ValueError, "missing"):
                compare_runs(baseline, candidate)

            contract = {
                "status": "failed",
                "profile": "smoke",
                "profile_settings": asdict(PROFILES["smoke"]),
                "passes": 1,
                "suites": ["ppl"],
                "evaluator_provenance": {"sha256": "same"},
                "failures": [{"name": "ppl"}],
            }
            for arm in (baseline, candidate):
                (arm / "run.json").write_text(json.dumps(contract))
                (arm / "summary.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "not eligible"):
                compare_runs(baseline, candidate)


if __name__ == "__main__":
    unittest.main()
