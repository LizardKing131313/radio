from __future__ import annotations

import subprocess


def main() -> int:
    """
    Дописать обновленный coverage badge в последний commit.
    """
    # Проверяем, изменился ли сгенерированный бейдж покрытия.
    diff = subprocess.run(["git", "diff", "--quiet", "--", "badges/coverage.svg"])
    # Если бейдж изменился, добавляем его в последний commit без смены сообщения.
    if diff.returncode != 0:
        subprocess.run(["git", "add", "badges/coverage.svg"], check=True)
        subprocess.run(["git", "commit", "--amend", "--no-edit"], check=False)
    # Скрипт используется как best-effort helper и всегда завершает CI успешно.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
