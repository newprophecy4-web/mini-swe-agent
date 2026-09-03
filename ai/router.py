from __future__ import annotations

from typing import Optional

from ai.base import AIProvider, ProviderFailure
from ai.providers.gemini import GeminiProvider
from ai.providers.openrouter import OpenRouterProvider


class AIRouter:
    def __init__(self, providers: Optional[list[AIProvider]] = None) -> None:
        self.providers = providers or [OpenRouterProvider()]

    def available(self) -> bool:
        return any(provider.available() for provider in self.providers)

    def status(self) -> list[dict]:
        return [provider.status() for provider in self.providers]

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        failures = []
        for provider in self.providers:
            if not provider.available():
                continue
            try:
                return await provider.generate(prompt, system, temperature)
            except ProviderFailure as exc:
                failures.append(f"{provider.name}: {exc.message}")
        if failures:
            raise ProviderFailure("; ".join(failures)[:800])
        raise ProviderFailure("No configured AI provider is available.")


work_router = AIRouter([OpenRouterProvider()])
chat_plan_router = AIRouter([GeminiProvider()])
ai_router = work_router
