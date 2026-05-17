from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts import precommit_pytest


def test_precommit_pytest_main_uses_project_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def fake_call(args: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append((args, cwd, env))
        return 7

    monkeypatch.setattr(precommit_pytest, "_project_python", lambda _root: Path("python"))
    monkeypatch.setattr(precommit_pytest.subprocess, "call", fake_call)
    monkeypatch.setenv("PYTHONPATH", "existing")

    assert precommit_pytest.main(["-q"]) == 7

    args, cwd, env = calls[0]
    assert args == ["python", "-m", "pytest", "-q"]
    assert cwd == Path(precommit_pytest.__file__).resolve().parents[1]
    pythonpath = env["PYTHONPATH"]
    assert "existing" in pythonpath
    assert str(cwd) in pythonpath


def test_project_python_prefers_windows_venv(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    assert precommit_pytest._project_python(tmp_path) == python


def test_project_python_falls_back_to_current_interpreter(tmp_path: Path) -> None:
    assert precommit_pytest._project_python(tmp_path) == Path(sys.executable)


def test_project_python_uses_wsl_venv(tmp_path: Path) -> None:
    python = tmp_path / ".venv-wsl" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    assert precommit_pytest._project_python(tmp_path) == python


def test_project_python_uses_posix_venv(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    assert precommit_pytest._project_python(tmp_path) == python
