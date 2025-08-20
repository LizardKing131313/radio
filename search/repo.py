from __future__ import annotations

import sqlite3
from typing import Any


DDL: str = (
    "CREATE TABLE IF NOT EXISTS videos("
    "  url TEXT PRIMARY KEY,"
    "  title TEXT,"
    "  uploader TEXT,"
    "  duration INTEGER,"
    "  view_count INTEGER,"
    "  upload_date TEXT,"
    "  thumbnail TEXT,"
    "  added_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
    ");"
)


def open_db(path: str) -> sqlite3.Connection:
    con: sqlite3.Connection = sqlite3.connect(path)
    con.execute(DDL)
    return con


def fetch_all_urls_set(con: sqlite3.Connection) -> set[str]:
    rows = con.execute("SELECT url FROM videos").fetchall()
    return {str(r[0]) for r in rows}


def _normalize_item(item: dict[str, Any]) -> tuple[str, Any, Any, Any, Any, Any, Any]:
    raw = item.get("webpage_url")
    if isinstance(raw, str) and raw.strip():
        url = raw.strip()
    else:
        vid = str(item.get("id") or "").strip()
        url = f"https://www.youtube.com/watch?v={vid}" if vid else ""
    return (
        url,
        item.get("title"),
        item.get("uploader"),
        item.get("duration"),
        item.get("view_count"),
        item.get("upload_date"),
        item.get("thumbnail"),
    )


def upsert(con: sqlite3.Connection, item: dict[str, Any]) -> None:
    sql = (
        "INSERT INTO videos(url,title,uploader,duration,view_count,upload_date,thumbnail) "
        "VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(url) DO UPDATE SET "
        "  title=excluded.title,"
        "  uploader=excluded.uploader,"
        "  duration=excluded.duration,"
        "  view_count=excluded.view_count,"
        "  upload_date=excluded.upload_date,"
        "  thumbnail=excluded.thumbnail"
    )
    con.execute(sql, _normalize_item(item))
    con.commit()
