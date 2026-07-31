import json
import re

from engine.providers.base import Message, Provider
from engine.verification.schema import enforce_critic_schema

LENSES = {
    "correctness": (
        "You are a strict, adversarial code reviewer focused ONLY on correctness: does the "
        "code do what the task asked, are there logic errors, edge cases, or bugs. Ignore "
        "style and security — those are reviewed separately."
    ),
    "security": (
        "You are a strict, adversarial code reviewer focused ONLY on security: injection "
        "risks, unsafe subprocess/eval usage, secrets handling, unvalidated input. Ignore "
        "correctness and style — those are reviewed separately."
    ),
    "code-quality": (
        "You are a strict, adversarial code reviewer focused ONLY on code quality: naming, "
        "structure, unnecessary complexity, dead code. Ignore correctness and security — "
        "those are reviewed separately."
    ),
}

CATEGORY_BY_LENS = {
    "correctness": "CORRECTNESS",
    "security": "SECURITY",
    "code-quality": "CODE-QUALITY",
}

RESPONSE_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON object, no prose before or after, no markdown fences:\n"
    '{"defects": [{"id": "C1", "category": "%s", "severity": "CRITICAL|HIGH|MEDIUM|LOW", '
    '"location": "path:line or description", "fix": "what to change"}], '
    '"verdict": "OK|FAIL"}\n'
    "verdict must be 'FAIL' iff at least one defect has severity CRITICAL or HIGH, else 'OK'. "
    "Return {\"defects\": [], \"verdict\": \"OK\"} if you find nothing to flag."
)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_critic(response_text: str) -> tuple[dict, list[str]]:
    match = _JSON_OBJECT_RE.search(response_text)
    if not match:
        return {}, ["response did not contain a JSON object"]
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return {}, [f"response was not valid JSON: {exc}"]
    errors = enforce_critic_schema(parsed)
    if errors:
        return {}, errors
    return parsed, []


def run_judge_gates(
    provider: Provider, model: str, task_text: str, code_snapshot: str
) -> tuple[list[dict], list[str]]:
    critics: list[dict] = []
    schema_errors: list[str] = []
    prompt = (
        f"Task given to the coding agent:\n{task_text}\n\n"
        f"Resulting code (all files concatenated):\n{code_snapshot}"
    )
    for lens_name, lens_system in LENSES.items():
        response = provider.generate(
            messages=[
                Message(
                    role="user",
                    content=prompt + RESPONSE_INSTRUCTION % CATEGORY_BY_LENS[lens_name],
                )
            ],
            model=model,
            system=lens_system,
            max_tokens=800,
        )
        critic, errors = _parse_critic(response.text)
        if errors:
            schema_errors.extend(f"judge:{lens_name}: {e}" for e in errors)
        else:
            critics.append(critic)
    return critics, schema_errors
