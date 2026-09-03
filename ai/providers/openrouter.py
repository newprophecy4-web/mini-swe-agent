from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Optional

import httpx

from ai.base import ProviderFailure


LOGGER = logging.getLogger("Open Agent")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider:
    name = "OpenRouter"

    def __init__(self) -> None:
        self.model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
        self._keys = tuple(
            value.strip()
            for name in (
                "OPENROUTER_API_KEY_1",
                "OPENROUTER_API_KEY_2",
                "OPENROUTER_API_KEY_3",
            )
            if (value := os.getenv(name, "").strip())
        )
        self._lock = threading.Lock()
        self._next_key = 0

    def available(self) -> bool:
        return bool(self._keys)

    def status(self) -> dict:
        return {
            "name": "openrouter",
            "configured": self.available(),
            "available": self.available(),
            "model": self.model,
            "configured_keys": len(self._keys),
        }

    def _ordered_keys(self) -> tuple[str, ...]:
        if not self._keys:
            return ()
        with self._lock:
            start = self._next_key % len(self._keys)
            self._next_key = (start + 1) % len(self._keys)
        return self._keys[start:] + self._keys[:start]

    @staticmethod
    def _retry_after(response: httpx.Response) -> Optional[float]:
        value = response.headers.get("retry-after")
        try:
            seconds = float(value) if value else 0
        except ValueError:
            return None
        return seconds if seconds > 0 else None

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error", {})
            message = error.get("message") if isinstance(error, dict) else None
            if message:
                return str(message)[:500]
        except (ValueError, TypeError):
            pass
        return f"OpenRouter returned HTTP {response.status_code}."

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        if not self._keys:
            raise ProviderFailure("No OpenRouter API key is configured.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if system and "Return ONLY valid JSON" in system:
            payload["response_format"] = {"type": "json_object"}
        last_failure: Optional[ProviderFailure] = None

        for key in self._ordered_keys():
            try:
                LOGGER.info("[AI] Provider: openrouter; Model: %s; Request started", self.model)
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        OPENROUTER_URL,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                            "X-OpenRouter-Title": "Open Agent",
                        },
                        json=payload,
                    )
                if response.status_code >= 400:
                    message = self._error_message(response)
                    last_failure = ProviderFailure(
                        message,
                        status_code=response.status_code,
                        retry_after=self._retry_after(response),
                    )
                    LOGGER.warning(
                        "[AI] OpenRouter request failed: status=%s message=%s",
                        response.status_code,
                        message,
                    )
                    if response.status_code == 400:
                        raise last_failure
                    if response.status_code in {401, 402, 403, 408, 429, 500, 502, 503, 504, 529}:
                        if last_failure.retry_after:
                            await asyncio.sleep(min(last_failure.retry_after, 30.0))
                        continue
                    continue

                data = response.json()
                choices = data.get("choices") or []
                content = choices[0].get("message", {}).get("content") if choices else None
                if not isinstance(content, str):
                    raise ProviderFailure("OpenRouter returned a malformed response.")
                LOGGER.info("[AI] OpenRouter request completed")
                return content.strip()
            except httpx.TimeoutException as exc:
                last_failure = ProviderFailure("OpenRouter request timed out.")
                LOGGER.warning("[AI] OpenRouter timeout: %s", type(exc).__name__)
            except httpx.RequestError as exc:
                last_failure = ProviderFailure("OpenRouter network request failed.")
                LOGGER.warning("[AI] OpenRouter network error: %s", type(exc).__name__)
            except ProviderFailure:
                raise

        raise last_failure or ProviderFailure("OpenRouter is unavailable.")
