from pathlib import Path

# M2: SQLite-backed cache of routing decisions per task-class, so the
# experiment in experiment.py only needs to run once per class and model set.


def get_cached_choice(db_path: Path, task_class: str) -> str | None:
    raise NotImplementedError("Routing decision cache lands in M2.")


def record_choice(db_path: Path, task_class: str, chosen_model: str, score: float) -> None:
    raise NotImplementedError("Routing decision cache lands in M2.")
