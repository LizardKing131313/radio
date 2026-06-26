from __future__ import annotations

from mimetypes import guess_type
from pathlib import Path as FsPath

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from manager.config import get_settings

router = APIRouter()

SHELL_CACHE_CONTROL = "no-cache"
ADMIN_SHELL_CACHE_CONTROL = "no-store"
STATIC_ASSET_CACHE_CONTROL = "public,max-age=31536000,immutable"


def web_root() -> FsPath:
    return get_settings().paths.www_html


def web_response(
    root: FsPath,
    relative_path: str,
    *,
    cache_control: str,
    media_type: str | None = None,
    missing_status: int = status.HTTP_404_NOT_FOUND,
) -> FileResponse:
    path = safe_web_path(root, relative_path)
    if not path.is_file():
        raise HTTPException(status_code=missing_status, detail="web client asset not found")
    response = FileResponse(path, media_type=media_type or guess_type(path.name)[0])
    response.headers["Cache-Control"] = cache_control
    return response


def safe_web_path(root: FsPath, relative_path: str) -> FsPath:
    resolved_root = root.resolve(strict=False)
    resolved_path = (resolved_root / relative_path).resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_root):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid asset path")
    return resolved_path


@router.get("/", include_in_schema=False)
@router.get("/player", include_in_schema=False)
@router.get("/player/{client_path:path}", include_in_schema=False)
def player_page(client_path: str = "") -> FileResponse:
    return web_response(
        web_root(),
        "apps/player/index.html",
        cache_control=SHELL_CACHE_CONTROL,
        media_type="text/html; charset=utf-8",
        missing_status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/admin", include_in_schema=False)
@router.get("/admin/{client_path:path}", include_in_schema=False)
def admin_page(client_path: str = "") -> FileResponse:
    return web_response(
        web_root(),
        "apps/admin/index.html",
        cache_control=ADMIN_SHELL_CACHE_CONTROL,
        media_type="text/html; charset=utf-8",
        missing_status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/assets/{asset_path:path}", include_in_schema=False)
def web_asset(asset_path: str) -> FileResponse:
    return web_response(
        web_root() / "assets",
        asset_path,
        cache_control=STATIC_ASSET_CACHE_CONTROL,
    )


@router.get("/icons/{icon_path:path}", include_in_schema=False)
def web_icon(icon_path: str) -> FileResponse:
    return web_response(web_root() / "icons", icon_path, cache_control=SHELL_CACHE_CONTROL)


@router.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest() -> FileResponse:
    return web_response(
        web_root(),
        "manifest.webmanifest",
        cache_control=SHELL_CACHE_CONTROL,
        media_type="application/manifest+json",
        missing_status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return web_response(
        web_root(),
        "sw.js",
        cache_control="no-cache",
        media_type="application/javascript; charset=utf-8",
        missing_status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return web_response(
        web_root(),
        "favicon.svg",
        cache_control=SHELL_CACHE_CONTROL,
        media_type="image/svg+xml",
    )
