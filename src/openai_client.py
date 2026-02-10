"""OpenAI API wrapper with retry, JSON mode, temp=0, and call logging."""

from __future__ import annotations

import json
import time
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Config
from .utils import ensure_dir, logger


class LLMClient:
    """Thin wrapper around the OpenAI chat completions API."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.model
        self._log_dir = ensure_dir(config.intermediate_dir / "api_calls")
        self._call_count = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _raw_chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = True,
        temperature: float = 0.0,
    ) -> str:
        """Make a single chat completion call with retry."""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        label: str = "api_call",
    ) -> str:
        """High-level API call with logging.

        Returns the raw response string. If json_mode=True, the caller is
        responsible for parsing JSON from the returned string.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self._call_count += 1
        call_id = f"{self._call_count:03d}_{label}"
        logger.info("API call #%d [%s] model=%s", self._call_count, label, self.model)

        if self.config.dry_run:
            logger.info("  DRY RUN — skipping actual API call")
            return '{"sections": [], "sources": [], "matches": []}'

        start = time.time()
        raw = self._raw_chat(messages, json_mode=json_mode)
        elapsed = time.time() - start
        logger.info("  Response received in %.1fs (%d chars)", elapsed, len(raw))

        # Log to file
        log_entry = {
            "call_id": call_id,
            "model": self.model,
            "elapsed_seconds": round(elapsed, 2),
            "system_prompt": system_prompt[:500],
            "user_prompt": user_prompt[:2000],
            "response": raw[:5000],
        }
        log_path = self._log_dir / f"{call_id}.json"
        log_path.write_text(json.dumps(log_entry, indent=2), encoding="utf-8")
        return raw

    def call_json(
        self,
        system_prompt: str,
        user_prompt: str,
        label: str = "api_call",
    ) -> dict:
        """Call API in JSON mode and parse the response."""
        raw = self.call(system_prompt, user_prompt, json_mode=True, label=label)
        return json.loads(raw)
