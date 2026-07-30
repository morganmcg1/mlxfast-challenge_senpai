from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class TokenizerError(RuntimeError):
    """The pinned Laguna tokenizer could not be loaded or used."""


class LagunaTokenizer:
    def __init__(self, directory: Path) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as error:
            raise TokenizerError(
                "transformers is required to serve quality evaluations; "
                "install the senpai/quality_eval Python environment"
            ) from error

        self.directory = directory
        template_path = directory / "chat_template.jinja"
        self.chat_template = template_path.read_text() if template_path.is_file() else None
        try:
            self.backend = AutoTokenizer.from_pretrained(
                str(directory),
                local_files_only=True,
                trust_remote_code=False,
            )
        except Exception as error:
            raise TokenizerError(f"cannot load tokenizer from {directory}: {error}") from error
        self.stop_token_ids = self._read_stop_token_ids(directory)

    @staticmethod
    def _read_stop_token_ids(directory: Path) -> list[int]:
        config_path = directory / "config.json"
        if not config_path.is_file():
            return [2, 24]
        try:
            eos = json.loads(config_path.read_text()).get("eos_token_id", [2, 24])
        except (OSError, json.JSONDecodeError):
            return [2, 24]
        values = eos if isinstance(eos, list) else [eos]
        return [int(value) for value in values]

    def encode_text(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        if not isinstance(text, str):
            raise TokenizerError("text must be a string")
        return list(self.backend.encode(text, add_special_tokens=add_special_tokens))

    def encode_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        add_generation_prompt: bool = True,
        enable_thinking: bool = False,
    ) -> list[int]:
        normalized = [
            {
                "role": str(message.get("role", "")),
                "content": self._message_text(message.get("content", "")),
            }
            for message in messages
        ]
        if any(not message["role"] for message in normalized):
            raise TokenizerError("each message requires a role")
        kwargs: dict[str, Any] = {
            "tokenize": True,
            "add_generation_prompt": add_generation_prompt,
            "enable_thinking": enable_thinking,
        }
        if self.chat_template is not None:
            kwargs["chat_template"] = self.chat_template
        try:
            token_ids = self.backend.apply_chat_template(normalized, **kwargs)
        except Exception as error:
            raise TokenizerError(f"cannot apply Laguna chat template: {error}") from error
        if isinstance(token_ids, Mapping):
            token_ids = token_ids.get("input_ids")
        if not isinstance(token_ids, list):
            raise TokenizerError("Laguna chat template did not return one token sequence")
        return [int(value) for value in token_ids]

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if not isinstance(part, dict) or part.get("type") not in (None, "text"):
                    raise TokenizerError("only text message content is supported")
                text = part.get("text", "")
                if not isinstance(text, str):
                    raise TokenizerError("message text blocks must contain strings")
                parts.append(text)
            return "".join(parts)
        raise TokenizerError("message content must be text")

    def decode(self, token_ids: list[int]) -> str:
        return str(
            self.backend.decode(
                token_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        )
