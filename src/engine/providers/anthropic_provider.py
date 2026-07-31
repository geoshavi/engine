from anthropic import Anthropic

from engine.providers.base import GenerationResult, Message


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self._client = Anthropic(api_key=api_key)

    def generate(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> GenerationResult:
        response = self._client.messages.create(
            model=model,
            system=system or "",
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return GenerationResult(
            text=text,
            model=model,
            provider=self.name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            raw=response,
        )
