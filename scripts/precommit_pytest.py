from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    python = _project_python(root)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (str(root), str(root / "scripts"), str(root / "manager"), env.get("PYTHONPATH"))
        if part
    )
    return subprocess.call([str(python), "-m", "pytest", *argv], cwd=root, env=env)


def _project_python(root: Path) -> Path:
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / ".venv-wsl" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
