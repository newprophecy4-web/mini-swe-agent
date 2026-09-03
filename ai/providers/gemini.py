from __future__ import annotations

import os
from typing import Optional

import httpx

from ai.base import ProviderFailure


class GeminiProvider:
    name = "Gemini"

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.chat_model = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash").strip()
        self.plan_model = os.getenv("GEMINI_PLAN_MODEL", self.chat_model).strip()

    def available(self) -> bool:
        return bool(self.api_key)

    def status(self) -> dict:
        return {
            "name": "gemini",
            "purpose": ["chat", "plan", "plan_finalize"],
            "configured": self.available(),
            "available": self.available(),
            "models": {"chat": self.chat_model, "plan": self.plan_model},
        }

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        if not self.api_key:
            raise ProviderFailure("No Gemini API key is configured.")

        model = (
            self.plan_model
            if "Create a professional software implementation plan." in prompt
            else self.chat_model
        )
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderFailure("Gemini request timed out.") from exc
        except httpx.RequestError as exc:
            raise ProviderFailure("Gemini network request failed.") from exc

        if response.status_code >= 400:
            raise ProviderFailure(
                f"Gemini returned HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderFailure("Gemini returned a malformed response.") from exc
        if not text.strip():
            raise ProviderFailure("Gemini returned an empty response.")
        return text.strip()
