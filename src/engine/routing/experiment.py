from engine.providers.base import Provider

# M2: given a task-class and a small candidate pool (2-3 models), run the task
# on each candidate under a fixed budget, score results via the verification
# pipeline, and pick a winner to cache in store.py.


def run_model_experiment(
    task_text: str, task_class: str, candidates: list[tuple[Provider, str]]
) -> str:
    raise NotImplementedError("Model-routing experimentation lands in M2.")
