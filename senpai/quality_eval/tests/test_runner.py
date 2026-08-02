from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any

QUALITY_EVAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUALITY_EVAL))

from laguna_quality.ppl_manifest import build_manifest

from laguna_quality.cli import _parse_attribute, build_parser
from laguna_quality.runner import (
    GPQA_DATASET_SEED,
    PROFILES,
    RANKED_GPQA_MAX_TOKENS,
    _compare_responses,
    _metric_comparison,
    _overall_score_comparison,
    _pass_commands,
    _required_behavior_matches,
    _regression_decision,
    _response_rows,
    _initialize_weave,
    _run_command_async,
    _run_weave_jobs,
    _validate_choice_output,
    _validate_quick_prompt_contract,
    _weave_score_summary,
    compare_runs,
    summarize_runs,
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


class CLITests(unittest.TestCase):
    def test_run_defaults_to_one_pass_and_accepts_gate_metadata(self) -> None:
        args = build_parser().parse_args(
            [
                "run",
                ".",
                "--profile",
                "full",
                "--baseline",
                "baseline",
                "--weave-project",
                "entity/project",
                "--change-label",
                "faster-moe",
                "--attribute",
                "hypothesis=fewer-copies",
            ]
        )
        self.assertIsNone(args.passes)
        self.assertEqual(args.baseline, Path("baseline"))
        self.assertEqual(args.weave_project, "entity/project")
        self.assertEqual(args.change_label, "faster-moe")
        self.assertEqual(
            _parse_attribute(args.attribute[0]),
            ("hypothesis", "fewer-copies"),
        )

    def test_attribute_requires_key_value_form(self) -> None:
        with self.assertRaisesRegex(ValueError, "KEY=VALUE"):
            _parse_attribute("missing-separator")


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
        standard_full_head_requests = (
            profile.mmlu_n
            + 2 * (profile.gpqa_limit or 0)
            + profile.gsm8k_n
        )
        aime_requests = profile.aime_limit or 0
        ranked_head_requests = profile.gpqa_limit or 0
        ppl_tokens = 8 * (profile.ppl_target_tokens or 0)

        self.assertEqual(
            standard_full_head_requests * profile.max_tokens
            + aime_requests * profile.aime_max_tokens
            + ranked_head_requests * RANKED_GPQA_MAX_TOKENS
            + ppl_tokens,
            64_896,
        )
        self.assertEqual(profile.max_connections, 1)
        self.assertEqual(profile.gpqa_limit, 9)
        self.assertEqual(profile.aime_limit, 9)
        self.assertEqual(profile.gsm8k_n, 6)
        self.assertEqual(profile.gpqa_sample_temperature, 0.5)
        self.assertFalse(profile.multiple_choice_cot)

    def test_quick_uses_frozen_question_manifests(self) -> None:
        commands = _pass_commands(
            pass_number=1,
            pass_dir=Path("/tmp/run/pass_1"),
            suites=("mmlu_pro", "gpqa_diamond", "aime", "gsm8k"),
            profile=PROFILES["quick"],
            base_url="http://127.0.0.1:1234",
            ppl_dataset=None,
            head_mode="full",
        )
        by_name = dict(commands)
        for name in (
            "mmlu_pro_greedy",
            "gpqa_diamond_greedy",
            "gpqa_diamond_sampled_s0",
            "aime_greedy",
            "gsm8k_greedy",
        ):
            self.assertIn("--ids-file", by_name[name])
        self.assertNotIn("--limit", by_name["gpqa_diamond_greedy"])
        self.assertEqual(
            by_name["gpqa_diamond_greedy"][
                by_name["gpqa_diamond_greedy"].index("--seed") + 1
            ],
            str(GPQA_DATASET_SEED),
        )

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
            self.assertNotIn("--no-cot", command)
            self.assertEqual(command[command.index("--min-tokens") + 1], "0")
            self.assertEqual(command[command.index("--max-tokens") + 1], "128")
            self.assertEqual(
                command[command.index("--prompt-format") + 1],
                "raw_single_user",
            )
        for _, command in full:
            self.assertNotIn("--prompt-format", command)
        for name, command in full:
            if name.startswith(("mmlu_pro", "gpqa_diamond")):
                self.assertIn("--no-cot", command)
        aime = dict(full)["aime_greedy"]
        self.assertEqual(
            aime[aime.index("--max-tokens") + 1],
            str(PROFILES["smoke"].aime_max_tokens),
        )


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


class OutputValidationTests(unittest.TestCase):
    def test_quality_choices_reject_truncation_but_ranked_proxy_allows_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            rows = [
                {
                    "id": "q1",
                    "prompt_sha": "prompt",
                    "completion": "partial",
                    "correct": False,
                    "stop_reason": "max_tokens",
                }
            ]
            dataset_sha = hashlib.sha256(
                json.dumps([["q1", "prompt"]], separators=(",", ":")).encode()
            ).hexdigest()
            path.write_text(
                json.dumps(
                    {
                        "accuracy": 0.0,
                        "n_samples": 1,
                        "n_expected": 1,
                        "n_scored": 1,
                        "n_correct": 0,
                        "n_error": 0,
                        "incomplete": False,
                        "dataset_sha256": dataset_sha,
                        "per_sample": rows,
                    }
                )
            )

            with self.assertRaisesRegex(ValueError, "truncated"):
                _validate_choice_output(path, 1)
            _validate_choice_output(path, 1, allow_length_truncation=True)

    def test_quick_prompt_contract_rejects_upstream_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pass_dir = Path(temporary)
            path = pass_dir / "mmlu_pro_greedy.json"
            expected = json.loads(
                (
                    QUALITY_EVAL
                    / "manifests"
                    / "quick_prompt_contract.json"
                ).read_text()
            )["mmlu_pro_greedy"]
            path.write_text(json.dumps({"dataset_sha256": expected}))
            _validate_quick_prompt_contract(pass_dir, ["mmlu_pro"])

            path.write_text(json.dumps({"dataset_sha256": "0" * 64}))
            with self.assertRaisesRegex(ValueError, "prompt contract drift"):
                _validate_quick_prompt_contract(pass_dir, ["mmlu_pro"])


class SummaryTests(unittest.TestCase):
    def test_overall_score_sums_questions_and_excludes_ppl_and_ranked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pass_dir = root / "pass_1"
            pass_dir.mkdir()
            files = {
                "ppl_summary.json": {"ppl": 13.0},
                "mmlu_pro_greedy.json": {
                    "accuracy": 9 / 20,
                    "n_correct": 9,
                    "n_expected": 20,
                },
                "gpqa_diamond_greedy.json": {
                    "accuracy": 6 / 9,
                    "n_correct": 6,
                    "n_expected": 9,
                },
                "gpqa_diamond_sampled_s0.json": {
                    "accuracy": 4 / 9,
                    "n_correct": 4,
                    "n_expected": 9,
                },
                "gpqa_diamond_ranked_greedy.json": {
                    "accuracy": 1.0,
                    "n_correct": 9,
                    "n_expected": 9,
                },
                "aime_greedy.json": {
                    "maj_k_accuracy": 4 / 9,
                    "n_correct_maj": 4,
                    "n_problems": 9,
                },
                "candidate_gsm8k_greedy.json": {
                    "accuracy": 0.5,
                    "n_correct": 3,
                    "n_problems": 6,
                },
            }
            for name, payload in files.items():
                (pass_dir / name).write_text(json.dumps(payload))

            arm = summarize_runs([root])["arms"][0]

            self.assertEqual(arm["overall_score"]["correct"], 26)
            self.assertEqual(arm["overall_score"]["total"], 53)
            self.assertEqual(arm["overall_score"]["score"], 26 / 53)
            self.assertEqual(
                set(arm["overall_score"]["components"]),
                {"mmlu", "gpqa_greedy", "gpqa_sampled", "aime", "gsm8k"},
            )


class WeaveEvaluationTests(unittest.TestCase):
    def test_weave_evaluation_runs_one_serial_trial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "order.txt"
            script = (
                "import json,sys; from pathlib import Path; "
                "marker=Path(sys.argv[1]); expected=sys.argv[2]; append=sys.argv[3]; "
                "actual=marker.read_text() if marker.exists() else ''; "
                "assert actual == expected; "
                "marker.write_text(actual + append); "
                "Path(sys.argv[4]).write_text(json.dumps("
                "{'accuracy': float(sys.argv[5]), 'n_correct': int(sys.argv[6]), "
                "'n_expected': int(sys.argv[7])}))"
            )
            jobs = []
            for name, expected, append, correct, total in (
                ("mmlu_pro_greedy", "", "a", 1, 2),
                ("gpqa_diamond_greedy", "a", "b", 2, 3),
            ):
                result_path = root / f"{name}.json"
                jobs.append(
                    {
                        "job_name": name,
                        "command": [
                            sys.executable,
                            "-c",
                            script,
                            str(marker),
                            expected,
                            append,
                            str(result_path),
                            str(correct / total),
                            str(correct),
                            str(total),
                        ],
                        "log_path": str(root / f"{name}.log"),
                        "result_path": str(result_path),
                        "category": "downstream",
                    }
                )
            weave, _ = _initialize_weave(None)
            outcomes, records = _run_weave_jobs(
                weave_module=weave,
                jobs=jobs,
                model_config={
                    "profile": "test",
                    "head_mode": "full",
                    "artifact_sha256": "artifact",
                    "git_commit": "commit",
                    "change_label": "test",
                },
                evaluation_metadata={"trials": 1},
                attributes={"test": "serial"},
                display_prefix="quality-test",
                keep_going=False,
            )

            self.assertEqual(marker.read_text(), "ab")
            self.assertEqual(set(outcomes), {job["job_name"] for job in jobs})
            self.assertTrue(all(row["status"] == "passed" for row in outcomes.values()))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["trials"], 1)
            self.assertEqual(records[0]["jobs"], [job["job_name"] for job in jobs])

    def test_weave_summary_fails_closed_on_partial_results(self) -> None:
        summary = _weave_score_summary(
            "downstream",
            [
                {"passed": True, "correct": 1, "total": 2},
                {"passed": False},
            ],
        )
        self.assertFalse(summary["passed"])
        self.assertIsNone(summary["overall_score"])

    def test_async_command_cancellation_reaps_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pid_path = root / "pid"

            async def cancel() -> int:
                task = asyncio.create_task(
                    _run_command_async(
                        [
                            sys.executable,
                            "-c",
                            (
                                "import os,sys,time; "
                                "open(sys.argv[1], 'w').write(str(os.getpid())); "
                                "time.sleep(60)"
                            ),
                            str(pid_path),
                        ],
                        root / "cancel.log",
                    )
                )
                for _ in range(100):
                    if pid_path.exists():
                        break
                    await asyncio.sleep(0.01)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                return int(pid_path.read_text())

            pid = asyncio.run(cancel())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


class ComparisonTests(unittest.TestCase):
    def test_ranked_gpqa_behavior_floor_scales_by_profile_size(self) -> None:
        for total, required in ((2, 2), (9, 7), (50, 39), (198, 154)):
            with self.subTest(total=total):
                self.assertEqual(_required_behavior_matches(total), required)

    def test_ranked_gpqa_behavior_floor_uses_extracted_responses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline"
            candidate = Path(temporary) / "candidate"
            for root in (baseline, candidate):
                (root / "pass_1").mkdir(parents=True)
            baseline_rows = [
                {"id": f"q{index}", "completion": f"answer-{index}"}
                for index in range(9)
            ]
            candidate_rows = [
                {
                    "id": row["id"],
                    "completion": (
                        row["completion"] if index < 7 else f"different-{index}"
                    ),
                }
                for index, row in enumerate(baseline_rows)
            ]
            filename = "gpqa_diamond_ranked_greedy.json"
            (baseline / "pass_1" / filename).write_text(
                json.dumps({"per_sample": baseline_rows})
            )
            (candidate / "pass_1" / filename).write_text(
                json.dumps({"per_sample": candidate_rows})
            )

            identity = _compare_responses(baseline, candidate)

            self.assertEqual(identity["ranked_gpqa"]["matched"], 7)
            self.assertEqual(identity["ranked_gpqa"]["required_matches"], 7)
            self.assertTrue(identity["ranked_gpqa"]["passed"])

            (candidate / "pass_1" / filename).write_text(
                json.dumps({"per_sample": baseline_rows})
            )
            for root in (baseline, candidate):
                (root / "pass_2").mkdir()
            second_candidate_rows = [
                {
                    "id": row["id"],
                    "completion": (
                        row["completion"] if index < 6 else f"different-{index}"
                    ),
                }
                for index, row in enumerate(baseline_rows)
            ]
            (baseline / "pass_2" / filename).write_text(
                json.dumps({"per_sample": baseline_rows})
            )
            (candidate / "pass_2" / filename).write_text(
                json.dumps({"per_sample": second_candidate_rows})
            )

            identity = _compare_responses(baseline, candidate)

            self.assertEqual(identity["ranked_gpqa"]["matched"], 15)
            self.assertEqual(identity["ranked_gpqa"]["required_matches"], 14)
            self.assertFalse(identity["ranked_gpqa"]["passed"])
            self.assertFalse(identity["ranked_gpqa"]["results"][1]["passed"])

    def test_ranked_gpqa_missing_candidate_row_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline" / "pass_1"
            candidate = Path(temporary) / "candidate" / "pass_1"
            baseline.mkdir(parents=True)
            candidate.mkdir(parents=True)
            rows = [
                {"id": f"q{index}", "completion": f"answer-{index}"}
                for index in range(9)
            ]
            filename = "gpqa_diamond_ranked_greedy.json"
            (baseline / filename).write_text(json.dumps({"per_sample": rows}))
            (candidate / filename).write_text(
                json.dumps({"per_sample": rows[:8]})
            )

            ranked = _compare_responses(
                baseline.parent,
                candidate.parent,
            )["ranked_gpqa"]

            self.assertEqual(ranked["total"], 9)
            self.assertEqual(ranked["compared"], 8)
            self.assertEqual(ranked["baseline_only"], 1)
            self.assertEqual(ranked["required_matches"], 7)
            self.assertEqual(ranked["match_rate"], 8 / 9)
            self.assertFalse(ranked["passed"])

    def test_ppl_rows_are_not_behavior_responses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pass_dir = Path(temporary) / "pass_1"
            pass_dir.mkdir()
            (pass_dir / "ppl_results.jsonl").write_text(
                json.dumps(
                    {
                        "id": "ppl-1",
                        "token_logprobs": [-1.0],
                        "ppl": 2.0,
                    }
                )
                + "\n"
            )

            self.assertEqual(_response_rows(Path(temporary)), {})

    def test_retention_gate_handles_metric_direction_and_response_budget(self) -> None:
        metrics = {
            "mmlu": _metric_comparison("mmlu", 0.80, 0.78),
            "ppl": _metric_comparison("ppl", 100.0, 102.0),
            "aime": _metric_comparison("aime", 0.0, 0.0),
            "overall_score": _overall_score_comparison(
                0.5,
                0.5,
                {"correct": 10, "total": 20},
                {"correct": 10, "total": 20},
            ),
        }
        response_identity = {
            "matched": 61,
            "total": 62,
            "match_rate": 61 / 62,
            "baseline_only": 0,
            "candidate_only": 0,
            "mismatches": [{"result": "mmlu", "id": "q1"}],
            "public_probe": {"matched": True},
            "ranked_gpqa": {
                "matched": 7,
                "total": 9,
                "required_matches": 7,
                "baseline_only": 0,
                "candidate_only": 0,
                "passed": True,
            },
        }

        decision = _regression_decision(metrics, response_identity)

        self.assertIsNone(metrics["mmlu"]["threshold"])
        self.assertIsNone(metrics["mmlu"]["gate_passed"])
        self.assertEqual(metrics["overall_score"]["threshold"], 0.485)
        self.assertEqual(metrics["overall_score"]["required_correct"], 10)
        self.assertAlmostEqual(metrics["ppl"]["threshold"], 100.0 / 0.97)
        self.assertFalse(metrics["aime"]["informative"])
        self.assertIsNone(metrics["aime"]["gate_passed"])
        self.assertTrue(
            _overall_score_comparison(
                1.0,
                0.97,
                {"correct": 100, "total": 100},
                {"correct": 97, "total": 100},
            )["gate_passed"]
        )
        self.assertFalse(
            _overall_score_comparison(
                1.0,
                0.96,
                {"correct": 100, "total": 100},
                {"correct": 96, "total": 100},
            )["gate_passed"]
        )
        self.assertTrue(
            _metric_comparison("ppl", 100.0, 100.0 / 0.97)["gate_passed"]
        )
        self.assertFalse(
            _metric_comparison("ppl", 100.0, 100.0 / 0.97 + 0.001)[
                "gate_passed"
            ]
        )
        self.assertEqual(decision["status"], "retained")
        self.assertTrue(decision["response_drift"])
        self.assertTrue(decision["local_retention_gate_passed"])
        self.assertEqual(decision["uninformative_metrics"], [])
        self.assertEqual(decision["monitor_only_metrics"], ["mmlu", "aime"])

        response_identity["ranked_gpqa"]["matched"] = 6
        response_identity["ranked_gpqa"]["passed"] = False
        decision = _regression_decision(metrics, response_identity)
        self.assertEqual(decision["status"], "regression")
        self.assertEqual(decision["metric_regressions"], [])
        self.assertFalse(decision["behavior_response_passed"])

        response_identity["ranked_gpqa"]["matched"] = 7
        response_identity["ranked_gpqa"]["passed"] = True
        metrics["overall_score"] = _overall_score_comparison(
            0.5,
            0.45,
            {"correct": 10, "total": 20},
            {"correct": 9, "total": 20},
        )
        decision = _regression_decision(metrics, response_identity)
        self.assertEqual(
            decision["metric_regressions"][0]["metric"],
            "overall_score",
        )

        response_identity["ranked_gpqa"] = {
            "matched": 0,
            "total": 0,
            "required_matches": 0,
            "baseline_only": 0,
            "candidate_only": 0,
            "passed": None,
        }
        metrics["overall_score"] = _overall_score_comparison(
            0.5,
            0.5,
            {"correct": 10, "total": 20},
            {"correct": 10, "total": 20},
        )
        response_identity["public_probe"] = {"matched": None}
        decision = _regression_decision(metrics, response_identity)
        self.assertIsNone(decision["behavior_response_passed"])
        self.assertIsNone(decision["public_probe_passed"])
        self.assertTrue(decision["local_retention_gate_passed"])

        decision = _regression_decision(
            {
                "overall_score": _overall_score_comparison(
                    0.0,
                    0.0,
                    {"correct": 0, "total": 20},
                    {"correct": 0, "total": 20},
                )
            },
            response_identity,
        )
        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertIsNone(decision["local_retention_gate_passed"])

        response_identity["public_probe"] = {"matched": True}
        decision = _regression_decision(
            {
                "overall_score": _overall_score_comparison(
                    0.0,
                    0.0,
                    {"correct": 0, "total": 20},
                    {"correct": 0, "total": 20},
                )
            },
            response_identity,
        )
        self.assertEqual(decision["status"], "insufficient_evidence")
        self.assertTrue(decision["public_probe_passed"])
        self.assertIsNone(decision["local_retention_gate_passed"])

        response_identity["public_probe"] = {"matched": False}
        decision = _regression_decision(
            {
                "overall_score": _overall_score_comparison(
                    0.0,
                    0.0,
                    {"correct": 0, "total": 20},
                    {"correct": 0, "total": 20},
                )
            },
            response_identity,
        )
        self.assertEqual(decision["status"], "regression")
        self.assertFalse(decision["local_retention_gate_passed"])

        response_identity["public_probe"] = {"matched": None}
        decision = _regression_decision(
            {
                "ppl": _metric_comparison("ppl", 100.0, 102.0),
                "mmlu": _metric_comparison("mmlu", None, None),
            },
            response_identity,
        )
        self.assertEqual(decision["informative_metrics"], ["ppl"])
        self.assertEqual(decision["uninformative_metrics"], [])
        self.assertEqual(decision["unavailable_metrics"], ["mmlu"])
        self.assertTrue(decision["local_retention_gate_passed"])

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
                                        },
                                        "overall_score": {
                                            "mean": accuracy,
                                            "stdev": 0.0,
                                            "n": 1,
                                        },
                                    },
                                    "overall_score": {
                                        "correct": int(accuracy * 2),
                                        "total": 2,
                                        "score": accuracy,
                                        "components": {
                                            "mmlu": {
                                                "correct": int(accuracy * 2),
                                                "total": 2,
                                                "score": accuracy,
                                            }
                                        },
                                        "passes": [
                                            {
                                                "pass": 1,
                                                "correct": int(accuracy * 2),
                                                "total": 2,
                                                "score": accuracy,
                                            }
                                        ],
                                    },
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
            self.assertIsNone(comparison["metrics"]["mmlu"]["gate_passed"])
            self.assertFalse(
                comparison["metrics"]["overall_score"]["gate_passed"]
            )
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
