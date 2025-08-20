from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import typer
import yaml

from .filters import explain_filters, pass_filters
from .make_queue import make_queue, write_queue
from .repo import fetch_all_urls_set, open_db, upsert
from .searcher import (
    YoutubeDL,
    list_channel,
    list_hashtag,
    list_playlist,
    search_queries,
)


app = typer.Typer(help="CLI для локального сборщика плейлистов")
BASE_DIR = Path(__file__).resolve().parent


def _load_cfg(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _normalize_url(item: dict[str, Any]) -> str:
    raw = item.get("webpage_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    vid = str(item.get("id") or "").strip()
    return f"https://www.youtube.com/watch?v={vid}" if vid else ""


def _apply_filters(cfg: dict[str, Any], item: dict[str, Any]) -> bool:
    f = cfg["filters"]
    # НОВОЕ: передаём список подстрок и режим OR
    return pass_filters(
        item,
        min_d=int(f["min_duration"]),
        max_d=int(f["max_duration"]),
        min_views=int(f["min_views"]),
        date_after=str(f["date_after"]),
        blacklist_rx=str(f["title_blacklist_rx"]),
        exclude_shorts=bool(f.get("exclude_shorts", False)),
        require_music=bool(f.get("require_music", False)),
        require_ai_marker=bool(f.get("require_ai_marker", False)),
        require_artist_ref=bool(f.get("require_artist_ref", False)),
        required_tag=(str(cfg.get("hashtag")).strip() if cfg.get("hashtag") else None),
        title_any=[str(s) for s in (f.get("title_any") or [])],
        tag_or_title=bool(f.get("tag_or_title", False)),
    )


@app.command()
def explain(
    url: str,
    config: str = str(BASE_DIR / "config.yaml"),
) -> None:
    cfg = _load_cfg(config)
    with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        data: dict[str, Any] = ydl.extract_info(url, download=False)
    f = cfg["filters"]
    reasons = explain_filters(
        data,
        min_d=int(f["min_duration"]),
        max_d=int(f["max_duration"]),
        min_views=int(f["min_views"]),
        date_after=str(f["date_after"]),
        blacklist_rx=str(f["title_blacklist_rx"]),
        exclude_shorts=bool(f.get("exclude_shorts", False)),
        require_music=bool(f.get("require_music", False)),
        require_ai_marker=bool(f.get("require_ai_marker", False)),
        require_artist_ref=bool(f.get("require_artist_ref", False)),
        required_tag=(str(cfg.get("hashtag")).strip() if cfg.get("hashtag") else None),
        title_any=[str(s) for s in (f.get("title_any") or [])],
        tag_or_title=bool(f.get("tag_or_title", False)),
    )
    if not reasons:
        typer.echo("✅ Проходит все фильтры")
    else:
        typer.echo("❌ Отсеян причинами: " + ", ".join(reasons))


@app.command()
def update_db(
    config: str = str(BASE_DIR / "config.yaml"),
    db: str = str(BASE_DIR / "db.sqlite"),
    per_query: int = 50,
    skip_existing: bool = True,
    verbose: bool = False,
) -> None:
    cfg = _load_cfg(config)
    con = open_db(db)
    known: set[str] = fetch_all_urls_set(con) if skip_existing else set()

    stats: Counter = Counter()

    def _consider(item: dict[str, Any]) -> None:
        url = _normalize_url(item)
        if skip_existing and url in known:
            stats["skip_existing"] += 1
            return

        if _apply_filters(cfg, item):
            upsert(con, item)
            stats["accepted"] += 1
            if skip_existing:
                known.add(url)
        else:
            reasons = explain_filters(
                item,
                min_d=int(cfg["filters"]["min_duration"]),
                max_d=int(cfg["filters"]["max_duration"]),
                min_views=int(cfg["filters"]["min_views"]),
                date_after=str(cfg["filters"]["date_after"]),
                blacklist_rx=str(cfg["filters"]["title_blacklist_rx"]),
                exclude_shorts=bool(cfg["filters"].get("exclude_shorts", False)),
                require_music=bool(cfg["filters"].get("require_music", False)),
                require_ai_marker=bool(cfg["filters"].get("require_ai_marker", False)),
                require_artist_ref=bool(cfg["filters"].get("require_artist_ref", False)),
                required_tag=(str(cfg.get("hashtag")).strip() if cfg.get("hashtag") else None),
                title_any=[str(s) for s in (cfg["filters"].get("title_any") or [])],
                tag_or_title=bool(cfg["filters"].get("tag_or_title", False)),
            )
            stats.update(reasons)
            if verbose:
                typer.echo(f"❌ {url} — {', '.join(reasons)}")

    # --- обход источников ---
    if cfg.get("hashtag"):
        for it in list_hashtag(str(cfg["hashtag"])):
            _consider(it)

    for it in search_queries(cfg.get("queries", []), per_query=per_query):
        _consider(it)

    for ch in cfg.get("channels", []) or []:
        for it in list_channel(ch):
            _consider(it)

    for pl in cfg.get("playlists", []) or []:
        for it in list_playlist(pl):
            _consider(it)

    # --- итоговый отчёт ---
    typer.echo("\n=== Update DB stats ===")
    for k, v in stats.most_common():
        typer.echo(f"{k:20s} {v}")
    typer.echo("=======================")


@app.command()
def build_queue(
    config: str = str(BASE_DIR / "config.yaml"),
    db: str = str(BASE_DIR / "db.sqlite"),
    out: str = str(BASE_DIR / "queue.txt"),
) -> None:
    cfg = _load_cfg(config)
    urls = make_queue(db, int(cfg["output"]["limit"]), bool(cfg["output"]["shuffle"]))
    write_queue(urls, out)
    typer.echo(f"Wrote {len(urls)} urls → {out}")


if __name__ == "__main__":
    app()
