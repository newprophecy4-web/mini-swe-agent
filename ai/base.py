from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class ProviderFailure(Exception):
    message: str
    status_code: Optional[int] = None
    retry_after: Optional[float] = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


class AIProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool:
        ...

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        ...

    def status(self) -> dict:
        ...
