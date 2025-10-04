from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from manager.prefetch.utils import iterate_files


@dataclass(slots=True)
class Metrics:
    hits: int = 0
    misses: int = 0
    errors: int = 0
    cold_used_bytes: int = 0
    cold_free_bytes: int = 0
    hot_count: int = 0
    last_loop_ts: float = 0.0

    def hit(self) -> None:
        self.hits += 1

    def miss(self) -> None:
        self.misses += 1

    def error(self) -> None:
        self.errors += 1

    def update_spaces(self, cold_dir: Path, hot_dir: Path, quota: int) -> None:
        used = 0
        for path in iterate_files(cold_dir):
            try:
                used += path.stat().st_size
            except Exception:
                continue
        self.cold_used_bytes = used
        self.cold_free_bytes = max(quota - used, 0)
        self.hot_count = sum(1 for _ in iterate_files(hot_dir))
        self.last_loop_ts = time.time()

    def as_dict(self) -> dict[str, Any]:
        denom = self.cold_used_bytes + self.cold_free_bytes
        pct = (self.cold_used_bytes / denom * 100.0) if denom else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "cold_used_bytes": self.cold_used_bytes,
            "cold_free_bytes": self.cold_free_bytes,
            "cold_used_pct": round(pct, 2),
            "hot_count": self.hot_count,
            "last_loop_ts": self.last_loop_ts,
        }


@dataclass(slots=True)
class BlacklistState:
    # Exponential backoff with per-id TTL in seconds
    # schema: { "youtube_id": {"fails": int, "until_ts": float} }
    data: dict[str, dict[str, float | int]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> BlacklistState:
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return cls(data=raw)
        except Exception:
            pass
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def skip(self, youtube_id: str) -> bool:
        rec = self.data.get(youtube_id)
        if not rec:
            return False
        return float(rec.get("until_ts", 0.0)) > time.time()

    def fail(self, youtube_id: str) -> None:
        rec = self.data.get(youtube_id) or {"fails": 0, "until_ts": 0.0}
        fails = int(rec.get("fails", 0)) + 1
        delay = min(3600, 30 * (2 ** (fails - 1)))  # 30s, 60s, 120s, ..., cap 1h
        self.data[youtube_id] = {"fails": fails, "until_ts": time.time() + delay}

    def reset(self, youtube_id: str) -> None:
        self.data.pop(youtube_id, None)

    def remove(self, youtube_id: str) -> None:
        self.data.pop(youtube_id, None)

    def clear(self) -> None:
        self.data.clear()


@dataclass(frozen=True, slots=True)
class ColdReady:
    youtube_id: str
    path: Path
