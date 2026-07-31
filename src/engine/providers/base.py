from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    raw: Any = field(default=None, repr=False)


class Provider(Protocol):
    name: str

    def generate(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> GenerationResult: ...
