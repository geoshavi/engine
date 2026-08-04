"""Tests for `engine bench`'s CLI integration -- specifically that --dry-run
makes zero LLM calls. Proven by succeeding with no API key configured at
all: if --dry-run ever reached LLMGateway.from_config()/build_provider(),
that would raise ValueError("ANTHROPIC_API_KEY is not set") instead of
exiting cleanly, so a clean exit is direct evidence no gateway was ever
constructed and no LLM call was structurally possible.
"""

import sys

import pytest

from engine import cli


def test_dry_run_succeeds_with_no_api_key_configured(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["engine", "bench", "--dry-run"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Benchmark plan:" in captured.out
    assert "Cases: 40" in captured.out


def test_dry_run_with_category_filters_the_plan(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["engine", "bench", "--dry-run", "--category", "security"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Cases: 10" in captured.out
    assert "Security: 10" in captured.out
    assert "Correctness: 0" in captured.out


def test_dry_run_with_compare_prints_an_explicit_warning_not_silence(monkeypatch, capsys) -> None:
    """--dry-run makes zero LLM calls, so there's nothing new to compare
    against #7 -- that must never be silently dropped.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["engine", "bench", "--dry-run", "--compare", "7"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "--compare" in captured.out
    assert "7" in captured.out
    assert "ignored" in captured.out
    # The plan itself still prints -- the warning doesn't replace the output.
    assert "Benchmark plan:" in captured.out


def test_dry_run_without_compare_prints_no_warning(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["engine", "bench", "--dry-run"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "WARNING" not in captured.out
