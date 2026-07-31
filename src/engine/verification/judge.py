from engine.providers.base import Message, Provider
from engine.state.models import VerificationResult

LENSES = {
    "correctness": (
        "You are a strict code reviewer focused ONLY on correctness: does the code do what the "
        "task asked, are there logic errors, edge cases, or bugs. Ignore style and security."
    ),
    "security": (
        "You are a strict code reviewer focused ONLY on security: injection risks, unsafe "
        "subprocess/eval usage, secrets handling, unvalidated input. Ignore style and correctness."
    ),
    "style": (
        "You are a strict code reviewer focused ONLY on style and maintainability: naming, "
        "structure, unnecessary complexity, dead code. Ignore correctness and security."
    ),
}

VERDICT_INSTRUCTION = (
    "\n\nRespond with exactly two parts:\n"
    "Line 1: 'VERDICT: PASS' or 'VERDICT: FAIL'\n"
    "Then a short justification (2-4 sentences)."
)


def _parse_verdict(text: str) -> bool:
    first_line = text.strip().splitlines()[0].upper() if text.strip() else ""
    return "PASS" in first_line and "FAIL" not in first_line


def run_judge_gates(
    provider: Provider, model: str, task_text: str, code_snapshot: str
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    prompt = (
        f"Task given to the coding agent:\n{task_text}\n\n"
        f"Resulting code (all files concatenated):\n{code_snapshot}"
    )
    for lens_name, lens_system in LENSES.items():
        response = provider.generate(
            messages=[Message(role="user", content=prompt + VERDICT_INSTRUCTION)],
            model=model,
            system=lens_system,
            max_tokens=500,
        )
        passed = _parse_verdict(response.text)
        results.append(VerificationResult(f"judge:{lens_name}", passed, response.text.strip()))
    return results
