from __future__ import annotations

import random
import sqlite3


def make_playlist(db: str, limit: int, shuffle: bool) -> list[str]:
    with sqlite3.connect(db) as con:
        # noinspection PyTypeChecker,SqlResolve
        cur: sqlite3.Cursor = con.execute(
            "SELECT url FROM videos " "ORDER BY upload_date DESC, view_count DESC " "LIMIT ?",
            (int(limit),),
        )
        rows = cur.fetchall()

    urls: list[str] = [str(r[0]) for r in rows]
    if shuffle:
        random.shuffle(urls)
    return urls


def write_playlist(urls: list[str], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for u in urls:
            f.write(u + "\n")
