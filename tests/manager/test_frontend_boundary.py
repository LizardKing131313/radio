from __future__ import annotations

from pathlib import Path


def test_backend_api_module_does_not_embed_browser_ui() -> None:
    source = Path("manager/api/app.py").read_text(encoding="utf-8")

    assert "ADMIN_HTML" not in source
    assert "<script>" not in source
    assert "<style>" not in source
    assert 'data-radio-app="admin"' not in source
