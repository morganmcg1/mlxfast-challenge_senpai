from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
QUALITY_EVAL = TESTS.parent
sys.path.insert(0, str(QUALITY_EVAL))

from laguna_quality.artifact import Artifact, ArtifactError, resolve_artifact
from laguna_quality.bridge import BridgeError, BridgeProcess
from laguna_quality.server import LagunaAPI, QualityHTTPServer, RequestJournal
from laguna_quality.run_lock import ModelRunLock, ModelRunLockError


class FakeTokenizer:
    stop_token_ids = [2, 24]

    def encode_text(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        prefix = [2] if add_special_tokens else []
        return prefix + [ord(character) for character in text]

    def encode_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        add_generation_prompt: bool = True,
        enable_thinking: bool = False,
    ) -> list[int]:
        text = "".join(str(message["content"]) for message in messages)
        return [2, int(enable_thinking), int(add_generation_prompt)] + [
            ord(character) for character in text
        ]

    def decode(self, token_ids: list[int]) -> str:
        return "".join(chr(token_id) for token_id in token_ids)


def fake_artifact(root: Path) -> Artifact:
    return Artifact(
        root=root,
        weights=root,
        tokenizer=root,
        bridge=TESTS / "fake_bridge.py",
        metallib=None,
        kind="test",
    )


class BridgeTests(unittest.TestCase):
    def test_persistent_request_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge = BridgeProcess(
                fake_artifact(Path(temporary)),
                command=[sys.executable, str(TESTS / "fake_bridge.py")],
            )
            with patch.dict(
                os.environ,
                {"DARKBLOOM_STARTUP_MEMORY_PROFILE": "low"},
            ):
                with bridge:
                    self.assertIsNone(bridge.ready["lm_head_prune"])
                    self.assertIsNone(bridge.ready["startup_profile"])
                    self.assertEqual(bridge.ready["head_mode"], "ranked")
                    first = bridge.request(
                        {
                            "kind": "generate",
                            "prompt_token_ids": [1],
                            "max_tokens": 2,
                            "seed": 0,
                        }
                    )
                    second = bridge.request(
                        {
                            "kind": "logprobs",
                            "prompt_token_ids": [1, 2, 3],
                            "score_start": 1,
                            "score_end": 3,
                        }
                    )
            self.assertEqual(first["token_ids"], [65, 24])
            self.assertEqual(second["token_logprobs"], [-1.0, -2.0])

    def test_full_logit_mode_disables_ranked_pruner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge = BridgeProcess(
                fake_artifact(Path(temporary)),
                command=[sys.executable, str(TESTS / "fake_bridge.py")],
                full_logits=True,
            )
            with bridge:
                self.assertEqual(bridge.ready["lm_head_prune"], "0")
                self.assertEqual(bridge.ready["head_mode"], "full")

    def test_protocol_error_closes_cleanly_and_can_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge = BridgeProcess(
                fake_artifact(Path(temporary)),
                command=[sys.executable, str(TESTS / "fake_bridge.py")],
            )
            with self.assertRaisesRegex(BridgeError, "does not match"):
                bridge.request(
                    {
                        "kind": "generate",
                        "prompt_token_ids": [1],
                        "max_tokens": 1,
                        "test_protocol": "wrong_id",
                    }
                )
            response = bridge.request(
                {
                    "kind": "generate",
                    "prompt_token_ids": [1],
                    "max_tokens": 1,
                    "seed": 1,
                }
            )
            bridge.close()
            self.assertEqual(response["token_ids"], [66, 24])

    def test_prompt_logprobs_reject_non_finite_bridge_values(self) -> None:
        class NonFiniteBridge:
            full_logits = True

            def request(self, request: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
                return {"token_logprobs": [float("nan")]}

        api = LagunaAPI(NonFiniteBridge(), FakeTokenizer())  # type: ignore[arg-type]
        with self.assertRaisesRegex(BridgeError, "finite"):
            api.completion(
                {
                    "model": "laguna-xs-2.1",
                    "prompt": [10, 11],
                    "prompt_logprobs": 1,
                }
            )

    def test_ranked_api_rejects_distribution_dependent_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge = BridgeProcess(
                fake_artifact(Path(temporary)),
                command=[sys.executable, str(TESTS / "fake_bridge.py")],
            )
            api = LagunaAPI(bridge, FakeTokenizer())
            with self.assertRaisesRegex(ValueError, "head-mode full"):
                api.completion(
                    {
                        "model": "laguna-xs-2.1",
                        "prompt": [10, 11],
                        "prompt_logprobs": 1,
                    }
                )
            with self.assertRaisesRegex(ValueError, "unmasked greedy"):
                api.chat_completion(
                    {
                        "model": "laguna-xs-2.1",
                        "messages": [{"role": "user", "content": "sample"}],
                        "temperature": 1.0,
                        "max_tokens": 1,
                    }
                )


class ArtifactTests(unittest.TestCase):
    def test_resolves_manifest_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "weights").mkdir()
            (root / "weights" / "config.json").write_text("{}")
            (root / "weights" / "model.safetensors.index.json").write_text("{}")
            (root / "weights" / "model-1.safetensors").write_bytes(b"x")
            (root / "tokenizer").mkdir()
            (root / "tokenizer" / "tokenizer.json").write_text("{}")
            (root / "tokenizer" / "chat_template.jinja").write_text("{{ messages }}")
            (root / "bin").mkdir()
            binary = root / "bin" / "laguna-quality-bridge"
            binary.write_text("#!/bin/sh\n")
            binary.chmod(0o755)
            (root / "quality-artifact.json").write_text(
                json.dumps(
                    {
                        "weights": "weights",
                        "tokenizer": "tokenizer",
                        "bridge": "bin/laguna-quality-bridge",
                    }
                )
            )

            artifact = resolve_artifact(root)

            self.assertEqual(artifact.kind, "bundle")
            self.assertEqual(artifact.weights, (root / "weights").resolve())
            self.assertEqual(artifact.tokenizer, (root / "tokenizer").resolve())
            self.assertEqual(artifact.bridge, binary.resolve())

    def test_rejects_bare_weights(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ArtifactError, "transformed weights"):
                resolve_artifact(temporary)


class ModelRunLockTests(unittest.TestCase):
    def test_serializes_model_owners_and_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"MLXFAST_LOCAL_RUN_LOCK_DIR": temporary},
        ):
            first = ModelRunLock("first")
            first.acquire()
            with self.assertRaisesRegex(ModelRunLockError, "another model run"):
                ModelRunLock("second").acquire()
            first.release()
            with ModelRunLock("third"):
                self.assertTrue(
                    (Path(temporary) / f"mlxfast-local-benchmark-{os.getuid()}.lock").is_dir()
                )


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.bridge = BridgeProcess(
            fake_artifact(root),
            command=[sys.executable, str(TESTS / "fake_bridge.py")],
            full_logits=True,
        )
        self.bridge.start()
        journal = RequestJournal(root / "requests.jsonl")
        self.journal_path = journal.path
        self.server = QualityHTTPServer(
            ("127.0.0.1", 0),
            LagunaAPI(self.bridge, FakeTokenizer()),
            journal=journal,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.bridge.close()
        self.temporary.cleanup()

    def get(self, path: str) -> dict[str, Any]:
        with urllib.request.urlopen(self.base_url + path) as response:
            return json.loads(response.read())

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def test_models_tokenize_chat_and_scoped_prompt_logprobs(self) -> None:
        models = self.get("/v1/models")
        self.assertEqual(models["data"][0]["id"], "laguna-xs-2.1")

        tokens = self.post(
            "/v1/tokenize",
            {
                "messages": [{"role": "user", "content": "hi"}],
                "add_generation_prompt": True,
            },
        )
        self.assertEqual(tokens["count"], 5)

        chat = self.post(
            "/v1/chat/completions",
            {
                "model": "laguna-xs-2.1",
                "messages": [{"role": "user", "content": "answer"}],
                "temperature": 0,
                "max_tokens": 4,
            },
        )
        self.assertEqual(chat["choices"][0]["message"]["content"], "A")
        self.assertEqual(chat["choices"][0]["finish_reason"], "stop")

        completion = self.post(
            "/v1/completions",
            {
                "model": "laguna-xs-2.1",
                "prompt": [10, 11, 12, 13, 14],
                "max_tokens": 1,
                "prompt_logprobs": 1,
                "score_token_start": 2,
                "score_token_end": 4,
            },
        )
        entries = completion["choices"][0]["prompt_logprobs"]
        self.assertEqual(entries, [None, None, {"12": -2.0}, {"13": -3.0}, None])

    def test_concurrent_http_requests_are_serialized_through_bridge(self) -> None:
        def request(seed: int) -> str:
            body = self.post(
                "/v1/chat/completions",
                {
                    "model": "laguna-xs-2.1",
                    "messages": [{"role": "user", "content": str(seed)}],
                    "temperature": 1,
                    "max_tokens": 2,
                    "seed": seed,
                },
            )
            return body["choices"][0]["message"]["content"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(request, range(16)))
        self.assertEqual(values, [chr(65 + seed) for seed in range(16)])

        journal = [json.loads(line) for line in self.journal_path.read_text().splitlines()]
        self.assertEqual(len(journal), 16)
        self.assertTrue(all(entry["status"] == 200 for entry in journal))


if __name__ == "__main__":
    unittest.main()
