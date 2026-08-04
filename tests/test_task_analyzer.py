from engine.orchestrator.task_analyzer import classify_task


def test_classify_task_returns_fixed_research_coding_testing_roles() -> None:
    analysis = classify_task("do the thing")

    assert analysis.required_roles == ["research", "coding", "testing"]
    assert analysis.task_class == "general"
    assert analysis.task_text == "do the thing"
    assert analysis.task_id


def test_classify_task_generates_a_unique_task_id_each_call() -> None:
    first = classify_task("do the thing")
    second = classify_task("do the thing")

    assert first.task_id != second.task_id
