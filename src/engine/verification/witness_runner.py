"""Fixed child entrypoint for witness execution -- see ``verification/witness.py``.

This script is engine code and never changes. It executes no model-supplied
source: there is no ``eval``, no ``exec``, no ``compile``, and no import name
that came from a model. It reads one JSON spec from stdin holding

  * ``modules`` -- candidate module names the *parent* derived from the
    workspace's own filenames,
  * ``call``    -- one attribute name, already validated as a plain identifier,
  * ``args``    -- JSON literals,

resolves the attribute, calls it, and prints a single JSON observation. Deciding
what that observation means is the parent's job, not this script's.

Only callables the reviewed module itself defines are eligible. A name the code
merely imported (``from os import system``) resolves to a foreign object and is
refused here -- otherwise a witness would be a way to invoke whatever the
reviewed file happened to import.
"""

import importlib
import json
import os
import sys
from typing import Any


def _resolve(modules: list[str], call: str) -> tuple[Any, str | None]:
    """(target, failure_outcome). Exactly one of the two is meaningful."""
    import_failed = False
    for name in modules:
        try:
            module = importlib.import_module(name)
        except BaseException:  # noqa: BLE001 -- any import failure is just "no observation"
            import_failed = True
            continue
        target = getattr(module, call, None)
        if target is None:
            continue
        if not callable(target):
            return None, "not_callable"
        if getattr(target, "__module__", None) != name:
            return None, "foreign_callable"
        return target, None
    return None, "import_error" if import_failed else "missing_callable"


def _observe(spec: dict) -> dict:
    # cwd goes on sys.path only now, after every import this script needs has
    # already happened -- a workspace file named json.py or importlib.py must
    # not be able to shadow the runner's own dependencies.
    sys.path.insert(0, os.getcwd())

    target, failure = _resolve(spec["modules"], spec["call"])
    if failure is not None:
        return {"outcome": failure}

    try:
        value = target(*spec["args"])
    except BaseException as exc:  # noqa: BLE001 -- classifying the exception IS the observation
        return {"outcome": "raised", "exc_type": type(exc).__name__}

    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return {"outcome": "unrepresentable"}
    return {"outcome": "returned", "value": value}


def main() -> None:
    print(json.dumps(_observe(json.loads(sys.stdin.read()))))


if __name__ == "__main__":
    main()
