"""Architecture protection: the Gateway must stay the only path to a live
provider. Three separate rules, each failing with the offending file and
which rule it broke, so a regression is diagnosable from the assertion
alone:

  Rule A: only runtime/ and providers/ may import a provider SDK directly.
  Rule B: only runtime/gateway.py may reach anything under providers/ that
          could construct or call a live provider. Implemented as an
          ALLOWLIST, not a blocklist: everything under providers/ is
          forbidden outside the Gateway EXCEPT the two specific things
          proven to carry no bypass risk --
            (1) any name from providers.base (Message, GenerationResult,
                the Provider Protocol type) -- pure data/typing, no way to
                make a real call. Every caller of gateway.generate() needs
                Message just to build its arguments, so forbidding it would
                make the Gateway's own public API unusable.
            (2) providers.registry.DEFAULT_MODELS specifically -- a plain
                dict of model-name strings, not anything that can call out.
          A blocklist (naming AnthropicProvider, build_provider, etc.)
          was tried first and missed `import engine.providers` reaching
          the same classes via attribute access -- an allowlist doesn't
          have that failure mode: anything not explicitly vetted is
          forbidden by construction, including bare/parent-package imports.
          Residual gap, acknowledged rather than silently ignored: a fully
          dynamic `importlib.import_module("engine.providers...")` has no
          import statement for AST to see at all. No static import scanner
          can close that; it would need a runtime import hook instead.
  Rule C: providers/ must not import runtime/ -- the dependency runs one
          way only (gateway -> provider). A cycle here would defeat the
          reason runtime/ lives outside orchestrator/ in the first place
          (so verification/ can import it without reaching into
          orchestrator/).
  Rule D: eval/ may only depend on verification/, runtime/, and state/
          (plus engine.config, needed everywhere, and stdlib/third-party).
          Everything else -- orchestrator/ (including agents/), providers/,
          api.py, cli.py, reporting/, routing/ -- is forbidden. This is
          stricter than "don't import providers/ or an SDK" (which Rule
          A/B already give eval/ for free by placement under src/engine/):
          it caught a real violation during development, where eval/runner.py
          imported write_files from orchestrator/agents/common.py. Fixed by
          giving eval/ its own minimal file-writer instead -- dataset file
          paths are hand-authored, not LLM output, so they don't need
          write_files()'s path-traversal guard in the first place.
  Rule E: verification/, runtime/, and state/ must never import eval/ --
          the dependency runs one way only (eval -> verification/runtime/
          state). Eval is a *client* of the review flow, not a dependency
          of it; those three packages must stay usable without eval/ ever
          being on the import path.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent / "src" / "engine"

# Extend as real SDKs are added (openai, google.generativeai, ollama, ...).
PROVIDER_SDK_MODULES = {"anthropic"}

# The only (module, name) pairs under providers/ considered safe to import
# outside the Gateway. Everything else under providers/ is forbidden --
# see Rule B docstring above for why this is an allowlist, not a blocklist.
ALLOWED_FROM_IMPORTS = {("engine.providers.registry", "DEFAULT_MODELS")}
ALLOWED_BASE_MODULE = "engine.providers.base"

GATEWAY_FILE = SRC_ROOT / "runtime" / "gateway.py"

# eval/'s allowed engine.* dependency surface -- see Rule D docstring above.
EVAL_ALLOWED_ENGINE_PACKAGES = {"engine.eval", "engine.verification", "engine.runtime", "engine.state"}
EVAL_ALLOWED_EXACT_MODULES = {"engine.config"}


def _iter_source_files() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.py"))


def _relative(path: Path) -> str:
    return str(path.relative_to(SRC_ROOT.parent.parent))


def _imported_module_names(path: Path) -> list[str]:
    """Module names from `import x` / `from x import y`, found anywhere in
    the file (not just top-level statements), so an import hidden inside a
    function or method doesn't slip past this check.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _bare_imported_modules(path: Path) -> list[str]:
    """Module names from `import x` statements only (not `from x import
    y`) -- checked separately by Rule B: a bare `import engine.providers`
    (or `import engine.providers.registry`, etc.) grants attribute access
    to whatever that module contains, so it's judged by module path alone,
    unlike `from x import y` which can be judged name-by-name.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]


def _imported_names(path: Path) -> list[tuple[str, str]]:
    """(module, imported_name) pairs from `from module import name`
    statements only.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            pairs.extend((node.module, alias.name) for alias in node.names)
    return pairs


def _is_in_package(path: Path, package_dir: str) -> bool:
    return (SRC_ROOT / package_dir) in path.parents


def test_rule_a_only_runtime_and_providers_import_the_sdk_directly() -> None:
    violations = []
    for path in _iter_source_files():
        if _is_in_package(path, "runtime") or _is_in_package(path, "providers"):
            continue
        for name in _imported_module_names(path):
            if name in PROVIDER_SDK_MODULES or any(
                name.startswith(f"{sdk}.") for sdk in PROVIDER_SDK_MODULES
            ):
                violations.append(f"{_relative(path)}: imports {name!r} (Rule A)")
    assert not violations, "Provider SDK imported outside runtime/ and providers/:\n" + "\n".join(
        violations
    )


def test_rule_b_only_gateway_imports_a_provider_implementation() -> None:
    violations = []
    for path in _iter_source_files():
        if _is_in_package(path, "providers") or path == GATEWAY_FILE:
            continue

        # `import engine.providers[...]` -- allowlist by module path, since
        # a bare import grants attribute access to everything inside it.
        for name in _bare_imported_modules(path):
            if name == "engine.providers" or (
                name.startswith("engine.providers.") and name != ALLOWED_BASE_MODULE
            ):
                violations.append(f"{_relative(path)}: imports {name!r} (Rule B)")

        # `from engine.providers.X import Y` -- allowlist by (module, name),
        # except providers.base where every name is safe (pure data/typing).
        for module, imported_name in _imported_names(path):
            if module == ALLOWED_BASE_MODULE:
                continue
            if module.startswith("engine.providers.") and (module, imported_name) not in ALLOWED_FROM_IMPORTS:
                violations.append(f"{_relative(path)}: imports {imported_name!r} from {module!r} (Rule B)")

    assert not violations, (
        "Only runtime/gateway.py may import something that can construct or call a live "
        "provider -- everything else must go through the Gateway:\n" + "\n".join(violations)
    )


def test_rule_c_providers_does_not_import_runtime() -> None:
    violations = []
    for path in _iter_source_files():
        if not _is_in_package(path, "providers"):
            continue
        for name in _imported_module_names(path):
            if name == "engine.runtime" or name.startswith("engine.runtime."):
                violations.append(f"{_relative(path)}: imports {name!r} (Rule C)")
    assert not violations, (
        "providers/ must not import runtime/ -- the dependency runs one way only "
        "(gateway -> provider):\n" + "\n".join(violations)
    )


def test_rule_d_eval_only_depends_on_verification_runtime_state() -> None:
    violations = []
    for path in _iter_source_files():
        if not _is_in_package(path, "eval"):
            continue
        for name in _imported_module_names(path):
            if not name.startswith("engine."):
                continue
            if name in EVAL_ALLOWED_EXACT_MODULES:
                continue
            if any(name == pkg or name.startswith(f"{pkg}.") for pkg in EVAL_ALLOWED_ENGINE_PACKAGES):
                continue
            violations.append(f"{_relative(path)}: imports {name!r} (Rule D)")
    assert not violations, (
        "eval/ may only depend on verification/, runtime/, and state/ (plus engine.config) -- "
        "orchestrator/, providers/, api.py, cli.py, reporting/, routing/ are all forbidden:\n"
        + "\n".join(violations)
    )


def test_rule_e_eval_is_never_imported_by_verification_runtime_state() -> None:
    violations = []
    for path in _iter_source_files():
        if _is_in_package(path, "eval"):
            continue
        if not (
            _is_in_package(path, "verification")
            or _is_in_package(path, "runtime")
            or _is_in_package(path, "state")
        ):
            continue
        for name in _imported_module_names(path):
            if name == "engine.eval" or name.startswith("engine.eval."):
                violations.append(f"{_relative(path)}: imports {name!r} (Rule E)")
    assert not violations, (
        "verification/, runtime/, and state/ must never import eval/ -- the dependency runs "
        "one way only (eval -> verification/runtime/state):\n" + "\n".join(violations)
    )
