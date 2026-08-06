import json
import re
import sqlite3
from collections.abc import Callable

from engine.providers.base import Message
from engine.runtime.budget import BudgetController
from engine.runtime.gateway import LLMGateway
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
        "You are a strict, adversarial code reviewer focused ONLY on code quality. First, "
        "check naming (a naming defect exists when an identifier creates a misleading "
        "contract about the function's actual behavior — for example, a getter name that "
        "also creates state; do not flag normal naming preferences). Then check magic "
        "numbers (only flag a literal when it represents configurable policy, a threshold, "
        "a limit, or a domain decision that would reasonably benefit from a named constant), "
        "structure, unnecessary complexity, dead code. Do NOT flag cryptographic parameters, "
        "protocol/algorithm constants, mathematical constants, one-off labels/messages, or "
        "obvious self-documenting values. Ignore correctness and security — those are "
        "reviewed separately."
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
    gateway: LLMGateway,
    budget: BudgetController,
    model: str,
    task_text: str,
    code_snapshot: str,
    *,
    run_id: int | None,
    task_id: str,
    conn: sqlite3.Connection | None,
    timeout_seconds: float | None = None,
    on_schema_failure: Callable[[str, str, list[str]], None] | None = None,
) -> tuple[list[dict], list[str]]:
    critics: list[dict] = []
    schema_errors: list[str] = []
    prompt = (
        f"Task given to the coding agent:\n{task_text}\n\n"
        f"Resulting code (all files concatenated):\n{code_snapshot}"
    )
    for lens_name, lens_system in LENSES.items():
        # Phase 2.1 scope note (deliberately NOT changed here): if this call
        # raises -- budget exceeded, network error, provider error -- the
        # exception propagates straight out of run_judge_gates, and any
        # critics already collected from earlier lenses in this loop are
        # discarded along with it; the caller never sees them. That's
        # intentional/out of scope for Phase 2.1, which only adds
        # observability for the success path -- it does not change judge
        # behavior. Per-lens fault isolation (catch here, return partial
        # critics plus a per-lens error marker instead of raising) is
        # future work: it would change what gate() sees when a lens fails,
        # which is a verdict-semantics decision, not an observability one.
        response = gateway.generate(
            budget=budget,
            messages=[
                Message(
                    role="user",
                    content=prompt + RESPONSE_INSTRUCTION % CATEGORY_BY_LENS[lens_name],
                )
            ],
            model=model,
            system=lens_system,
            max_tokens=800,
            agent_name=f"judge:{lens_name}",
            run_id=run_id,
            task_id=task_id,
            conn=conn,
            timeout_seconds=timeout_seconds,
        )
        critic, errors = _parse_critic(response.text)
        if errors:
            schema_errors.extend(f"judge:{lens_name}: {e}" for e in errors)
            if on_schema_failure is not None:
                # response.text is typed str, but normalize defensively --
                # callers persist this raw text and must never see None.
                on_schema_failure(lens_name, response.text or "", errors)
        else:
            # Tag by the lens that actually produced this defect, not by
            # its self-reported "category" -- the two are expected to
            # agree (each lens's prompt fixes its category string) but
            # nothing enforces that a defect's category matches the lens
            # that emitted it, and eval/'s observability tables need the
            # ground truth of which lens ran, not the model's claim.
            for defect in critic.get("defects", []):
                defect["lens"] = lens_name
            critics.append(critic)
    return critics, schema_errors
