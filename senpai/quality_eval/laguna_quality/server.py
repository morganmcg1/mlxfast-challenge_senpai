from __future__ import annotations

import json
import math
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .bridge import BridgeError, BridgeProcess
from .tokenizer import TokenizerError

MODEL_NAME = "laguna-xs-2.1"
MAX_REQUEST_BYTES = 32 * 1024 * 1024
CHAT_PROMPT_FORMAT = "chat_template"
RAW_SINGLE_USER_PROMPT_FORMAT = "raw_single_user"


class APIError(ValueError):
    pass


class Tokenizer(Protocol):
    stop_token_ids: list[int]

    def encode_text(self, text: str, *, add_special_tokens: bool = True) -> list[int]: ...

    def encode_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        add_generation_prompt: bool = True,
        enable_thinking: bool = False,
    ) -> list[int]: ...

    def decode(self, token_ids: list[int]) -> str: ...


@dataclass
class RequestJournal:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self.path.open("a") as output:
            output.write(line + "\n")


class LagunaAPI:
    def __init__(
        self,
        bridge: BridgeProcess,
        tokenizer: Tokenizer,
        *,
        model: str = MODEL_NAME,
        request_timeout: float | None = None,
    ) -> None:
        self.bridge = bridge
        self.tokenizer = tokenizer
        self.model = model
        self.request_timeout = request_timeout

    def tokenize(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_text = "text" in payload
        has_messages = "messages" in payload
        if has_text == has_messages:
            raise APIError("provide exactly one of text or messages")
        if has_text:
            token_ids = self.tokenizer.encode_text(
                self._string(payload, "text"),
                add_special_tokens=self._boolean(payload, "add_special_tokens", True),
            )
        else:
            token_ids = self.tokenizer.encode_messages(
                self._messages(payload),
                add_generation_prompt=self._boolean(payload, "add_generation_prompt", True),
                enable_thinking=self._thinking(payload),
            )
        return {"object": "tokens", "token_ids": token_ids, "count": len(token_ids)}

    def chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._common(payload)
        messages = self._messages(payload)
        prompt_format = payload.get("prompt_format", CHAT_PROMPT_FORMAT)
        if prompt_format == CHAT_PROMPT_FORMAT:
            prompt_ids = self.tokenizer.encode_messages(
                messages,
                add_generation_prompt=True,
                enable_thinking=self._thinking(payload),
            )
        elif prompt_format == RAW_SINGLE_USER_PROMPT_FORMAT:
            prompt_ids = self._raw_single_user_prompt(messages)
        else:
            raise APIError(
                f"prompt_format must be {CHAT_PROMPT_FORMAT!r} or "
                f"{RAW_SINGLE_USER_PROMPT_FORMAT!r}"
            )
        choices, generated_count = self._generate_choices(payload, prompt_ids, chat=True)
        return self._completion_envelope("chat.completion", payload, prompt_ids, choices, generated_count)

    def completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._common(payload)
        prompt = payload.get("prompt")
        if self._is_token_prompt(prompt):
            prompt_ids = [int(value) for value in prompt]
        elif isinstance(prompt, str):
            prompt_ids = self.tokenizer.encode_text(
                prompt,
                add_special_tokens=self._boolean(payload, "add_special_tokens", True),
            )
        else:
            raise APIError("prompt must be a string or one integer-token sequence")
        if not prompt_ids:
            raise APIError("prompt must not be empty")

        if payload.get("prompt_logprobs") is not None:
            return self._prompt_logprobs(payload, prompt_ids)
        choices, generated_count = self._generate_choices(payload, prompt_ids, chat=False)
        return self._completion_envelope(
            "text_completion", payload, prompt_ids, choices, generated_count
        )

    def _prompt_logprobs(
        self, payload: dict[str, Any], prompt_ids: list[int]
    ) -> dict[str, Any]:
        if not self.bridge.full_logits:
            raise APIError("prompt_logprobs requires --head-mode full")
        if len(prompt_ids) < 2:
            raise APIError("prompt_logprobs requires at least two prompt tokens")
        score_start = self._integer(payload, "score_token_start", 1, minimum=1)
        score_end = self._integer(
            payload, "score_token_end", len(prompt_ids), minimum=score_start
        )
        if score_end > len(prompt_ids):
            raise APIError("score_token_end exceeds the prompt length")
        if score_start == score_end:
            raise APIError("prompt logprob score range must not be empty")
        response = self.bridge.request(
            {
                "kind": "logprobs",
                "prompt_token_ids": prompt_ids,
                "score_start": score_start,
                "score_end": score_end,
            },
            timeout=self.request_timeout,
        )
        values = response.get("token_logprobs")
        expected = score_end - score_start
        if not isinstance(values, list) or len(values) != expected:
            raise BridgeError(
                "bridge returned "
                f"{len(values) if isinstance(values, list) else 'invalid'} token logprobs "
                f"for {expected} scored positions"
            )
        prompt_logprobs: list[dict[str, float] | None] = [None] * len(prompt_ids)
        for index, value in zip(range(score_start, score_end), values, strict=True):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise BridgeError("bridge token_logprobs must contain finite numbers")
            prompt_logprobs[index] = {str(prompt_ids[index]): float(value)}
        choice = {
            "index": 0,
            "text": "",
            "finish_reason": "length",
            "prompt_logprobs": prompt_logprobs,
        }
        return self._completion_envelope(
            "text_completion", payload, prompt_ids, [choice], generated_count=0
        )

    def _generate_choices(
        self, payload: dict[str, Any], prompt_ids: list[int], *, chat: bool
    ) -> tuple[list[dict[str, Any]], int]:
        maximum = self._integer(payload, "max_tokens", 16, minimum=0)
        if maximum == 0:
            return [self._choice(0, [], "length", chat, payload)], 0
        count = self._integer(payload, "n", 1, minimum=1, maximum=64)
        temperature = self._number(payload, "temperature", 1.0, minimum=0.0)
        top_p = self._number(payload, "top_p", 1.0, minimum=0.0, maximum=1.0)
        if top_p == 0:
            raise APIError("top_p must be greater than zero")
        top_k = self._integer(payload, "top_k", 0, minimum=-1)
        seed = self._integer(
            payload,
            "seed",
            0,
            minimum=0,
            maximum=(1 << 64) - count,
        )
        min_tokens = self._integer(payload, "min_tokens", 0, minimum=0)
        if min_tokens > maximum:
            raise APIError("min_tokens cannot exceed max_tokens")
        if not self.bridge.full_logits and (temperature != 0 or min_tokens != 0):
            raise APIError(
                "ranked head supports only unmasked greedy generation; "
                "use --head-mode full"
            )

        choices: list[dict[str, Any]] = []
        generated_count = 0
        for index in range(count):
            response = self.bridge.request(
                {
                    "kind": "generate",
                    "prompt_token_ids": prompt_ids,
                    "max_tokens": maximum,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "seed": seed + index,
                    "min_tokens": min_tokens,
                    "stop_token_ids": self.tokenizer.stop_token_ids,
                },
                timeout=self.request_timeout,
            )
            raw_ids = response.get("token_ids")
            if not isinstance(raw_ids, list) or any(
                not isinstance(value, int) for value in raw_ids
            ):
                raise BridgeError("bridge generate response has invalid token_ids")
            finish_reason = self._finish_reason(response.get("finish_reason"))
            generated_count += len(raw_ids)
            visible_ids = list(raw_ids)
            if visible_ids and visible_ids[-1] in self.tokenizer.stop_token_ids:
                visible_ids.pop()
                finish_reason = "stop"
            choices.append(self._choice(index, visible_ids, finish_reason, chat, payload))
        return choices, generated_count

    def _choice(
        self,
        index: int,
        token_ids: list[int],
        finish_reason: str,
        chat: bool,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        text = self._truncate_stop_text(self.tokenizer.decode(token_ids), payload.get("stop"))
        if text[1]:
            finish_reason = "stop"
        content = text[0]
        if chat:
            return {
                "index": index,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
                "token_ids": token_ids,
            }
        return {
            "index": index,
            "text": content,
            "finish_reason": finish_reason,
            "token_ids": token_ids,
        }

    def _completion_envelope(
        self,
        object_name: str,
        payload: dict[str, Any],
        prompt_ids: list[int],
        choices: list[dict[str, Any]],
        generated_count: int,
    ) -> dict[str, Any]:
        prefix = "chatcmpl" if object_name == "chat.completion" else "cmpl"
        return {
            "id": f"{prefix}-{uuid.uuid4().hex}",
            "object": object_name,
            "created": int(time.time()),
            "model": self.model,
            "choices": choices,
            "usage": {
                "prompt_tokens": len(prompt_ids),
                "completion_tokens": generated_count,
                "total_tokens": len(prompt_ids) + generated_count,
            },
        }

    def _common(self, payload: dict[str, Any]) -> None:
        model = payload.get("model", self.model)
        if model != self.model:
            raise APIError(f"unknown model {model!r}; use {self.model!r}")
        if payload.get("stream", False):
            raise APIError("streaming responses are not supported")

    @staticmethod
    def _messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise APIError("messages must be a non-empty list")
        if any(not isinstance(message, dict) for message in messages):
            raise APIError("each message must be an object")
        return messages

    def _raw_single_user_prompt(self, messages: list[dict[str, Any]]) -> list[int]:
        if (
            len(messages) != 1
            or messages[0].get("role") != "user"
            or not isinstance(messages[0].get("content"), str)
        ):
            raise APIError(
                "raw_single_user prompt_format requires exactly one user message "
                "with string content"
            )
        return self.tokenizer.encode_text(
            messages[0]["content"],
            add_special_tokens=True,
        )

    @staticmethod
    def _is_token_prompt(value: Any) -> bool:
        return isinstance(value, list) and all(
            isinstance(token_id, int) and not isinstance(token_id, bool)
            for token_id in value
        )

    @staticmethod
    def _thinking(payload: dict[str, Any]) -> bool:
        kwargs = payload.get("chat_template_kwargs", {})
        if kwargs is None:
            return False
        if not isinstance(kwargs, dict):
            raise APIError("chat_template_kwargs must be an object")
        value = kwargs.get("enable_thinking", False)
        if not isinstance(value, bool):
            raise APIError("enable_thinking must be boolean")
        return value

    @staticmethod
    def _finish_reason(value: Any) -> str:
        return "stop" if value in ("stop", "eos") else "length"

    @staticmethod
    def _truncate_stop_text(text: str, stop: Any) -> tuple[str, bool]:
        if stop is None:
            return text, False
        stops = [stop] if isinstance(stop, str) else stop
        if not isinstance(stops, list) or any(not isinstance(item, str) for item in stops):
            raise APIError("stop must be a string or list of strings")
        positions = [text.find(item) for item in stops if item and text.find(item) >= 0]
        return (text[: min(positions)], True) if positions else (text, False)

    @staticmethod
    def _string(payload: dict[str, Any], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str):
            raise APIError(f"{name} must be a string")
        return value

    @staticmethod
    def _boolean(payload: dict[str, Any], name: str, default: bool) -> bool:
        value = payload.get(name, default)
        if not isinstance(value, bool):
            raise APIError(f"{name} must be boolean")
        return value

    @staticmethod
    def _integer(
        payload: dict[str, Any],
        name: str,
        default: int,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        value = payload.get(name, default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise APIError(f"{name} must be an integer")
        if minimum is not None and value < minimum:
            raise APIError(f"{name} must be at least {minimum}")
        if maximum is not None and value > maximum:
            raise APIError(f"{name} must be at most {maximum}")
        return value

    @staticmethod
    def _number(
        payload: dict[str, Any],
        name: str,
        default: float,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        value = payload.get(name, default)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise APIError(f"{name} must be a number")
        result = float(value)
        if not math.isfinite(result):
            raise APIError(f"{name} must be finite")
        if minimum is not None and result < minimum:
            raise APIError(f"{name} must be at least {minimum}")
        if maximum is not None and result > maximum:
            raise APIError(f"{name} must be at most {maximum}")
        return result


class QualityHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        api: LagunaAPI,
        *,
        journal: RequestJournal | None = None,
    ) -> None:
        self.api = api
        self.journal = journal
        super().__init__(address, QualityRequestHandler)


class QualityRequestHandler(BaseHTTPRequestHandler):
    server: QualityHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "laguna-quality/1"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/health", "/healthz"):
            self._write(HTTPStatus.OK, {"status": "ok", "model": self.server.api.model})
            return
        if path == "/v1/models":
            self._write(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.server.api.model,
                            "object": "model",
                            "created": 0,
                            "owned_by": "local",
                        }
                    ],
                },
            )
            return
        self._error(HTTPStatus.NOT_FOUND, f"unknown endpoint {path}")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        started = time.time()
        request_id = uuid.uuid4().hex
        payload: dict[str, Any] | None = None
        response: dict[str, Any] | None = None
        status = HTTPStatus.OK
        try:
            payload = self._read_json()
            if path == "/v1/chat/completions":
                response = self.server.api.chat_completion(payload)
            elif path == "/v1/completions":
                response = self.server.api.completion(payload)
            elif path == "/v1/tokenize":
                response = self.server.api.tokenize(payload)
            else:
                raise APIError(f"unknown endpoint {path}")
        except (APIError, TokenizerError) as error:
            status = HTTPStatus.BAD_REQUEST
            response = self._error_body(str(error), "invalid_request_error")
        except BridgeError as error:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            response = self._error_body(str(error), "bridge_error")
        except Exception as error:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            response = self._error_body(str(error), "server_error")
        assert response is not None
        if self.server.journal:
            self.server.journal.write(
                {
                    "request_id": request_id,
                    "endpoint": path,
                    "status": int(status),
                    "duration_s": time.time() - started,
                    "request": payload,
                    "response": response,
                }
            )
        self._write(status, response)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as error:
            raise APIError("invalid Content-Length") from error
        if length <= 0:
            raise APIError("request body must not be empty")
        if length > MAX_REQUEST_BYTES:
            raise APIError(f"request exceeds {MAX_REQUEST_BYTES} bytes")
        try:
            value = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as error:
            raise APIError(f"invalid JSON: {error.msg}") from error
        if not isinstance(value, dict):
            raise APIError("request JSON must be an object")
        return value

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._write(status, self._error_body(message, "invalid_request_error"))

    @staticmethod
    def _error_body(message: str, kind: str) -> dict[str, Any]:
        return {"error": {"message": message, "type": kind, "code": None}}

    def _write(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[quality-api] {self.address_string()} {format % args}\n")
