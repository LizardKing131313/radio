from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
from pathlib import Path

from manager.config import AppConfig, get_settings
from manager.logger import get_logger
from manager.prefetch.data import BlacklistState, Metrics
from manager.prefetch.utils import SuppressTask, iterate_files, proc_exec, watch_url
from manager.track_queue.db import Database
from manager.track_queue.models import Track
from manager.track_queue.repo import TracksRepo

AUDIO_SUFFIXES = {".opus"}


class PrefetchWorker:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or get_settings()
        self.log = get_logger("prefetch")
        # Воркер ходит в Postgres напрямую. Старый внутренний раннер/шина сообщений
        # удален, потому что оркестрацию теперь делает Kubernetes.
        self.database = Database(app_config=self.config)
        self.tracks = TracksRepo(self.database)
        self.metrics = Metrics()
        self.blacklist = BlacklistState.load(self.config.paths.cache_blacklist)

    async def run_forever(self) -> None:
        self.database.ensure_schema()
        self._ensure_dirs()

        while True:
            try:
                await self.tick()
            except Exception as exception:
                self.log.warning("prefetch tick failed", error=str(exception))
            await asyncio.sleep(max(1, self.config.prefetch.interval_sec))

    async def tick(self) -> None:
        # Холодный кеш живет на PVC. Горячий кеш - маленький рабочий набор, который
        # Liquidsoap смотрит для ближайшего проигрывания.
        await self._cleanup_non_audio_cache()
        await self._enforce_cold_quota()
        items = self.tracks.get_missing_audio(self.config.prefetch.batch_size)
        await self._process_tracks(items)
        await self._refresh_hot_cache()
        self.metrics.update_spaces(
            self.config.paths.cache_cold,
            self.config.paths.cache_hot,
            self.config.prefetch.cold_quota_bytes,
        )
        self.blacklist.save(self.config.paths.cache_blacklist)

    async def _process_tracks(self, items: list[Track]) -> None:
        # Ограничиваем параллельность, чтобы не забить сеть/диск пачкой yt-dlp.
        semaphore = asyncio.Semaphore(max(1, self.config.prefetch.concurrent_downloads))

        async def worker(track: Track) -> None:
            async with semaphore:
                await self._process_track(track)

        await asyncio.gather(*(worker(track) for track in items))

    async def _process_track(self, track: Track) -> None:
        # Временно битые YouTube id пропускаются через маленький JSON blacklist;
        # постоянное состояние трека все равно остается в Postgres.
        if self.blacklist.skip(track.youtube_id):
            return

        cold_path = self.config.paths.cache_cold / f"{track.youtube_id}.opus"
        try:
            if cold_path.exists():
                self.metrics.hit()
                await self._ensure_hot_copy(cold_path)
                self.tracks.update_track_audio(track_id=track.id, audio_path=str(cold_path))
                self.blacklist.reset(track.youtube_id)
                return

            if await self._download_opus(track, cold_path):
                self.metrics.miss()
                lufs = await self._measure_lufs(cold_path)
                await self._ensure_hot_copy(cold_path)
                self.tracks.update_track_audio(
                    track_id=track.id,
                    audio_path=str(cold_path),
                    loudness_lufs=lufs,
                )
                self.blacklist.reset(track.youtube_id)
                return

            self.metrics.error()
            self.blacklist.fail(track.youtube_id)
            self.tracks.increment_fail_count(track.id)
        except Exception as exception:
            self.log.warning(
                "track prefetch failed", youtube_id=track.youtube_id, error=str(exception)
            )
            self.metrics.error()
            self.blacklist.fail(track.youtube_id)
            self.tracks.increment_fail_count(track.id)

    async def _download_opus(self, track: Track, out_path: Path) -> bool:
        out_template = str(out_path.with_name("%(id)s.%(ext)s"))
        # Поиск идет через YouTube Data API. yt-dlp остается только здесь, где
        # реально нужен аудиофайл.
        args = [
            "yt-dlp",
            track.url or watch_url(track.youtube_id),
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "opus",
            "--audio-quality",
            "0",
            "--add-metadata",
            "--parse-metadata",
            "title:%(title)s",
            "--parse-metadata",
            "artist:%(uploader)s",
            "--output",
            out_template,
            "--no-part",
            "--no-overwrites",
            "--quiet",
            # YouTube иногда требует JS challenge. Node в образе нужен именно
            # yt-dlp, поиск все равно остается на YouTube Data API.
            "--js-runtimes",
            "node",
        ]
        if self.config.paths.cookies.exists():
            args += ["--cookies", str(self.config.paths.cookies)]

        code, _out, error = await proc_exec(
            *args, timeout=self.config.prefetch.download_timeout_sec
        )
        if code != 0:
            self.log.warning("yt-dlp failed", youtube_id=track.youtube_id, code=code, error=error)
            return False
        return out_path.exists()

    async def _measure_lufs(self, path: Path) -> float | None:
        # LUFS нужен для будущей нормализации/аналитики; ошибка не блокирует трек.
        code, _out, error = await proc_exec(
            "ffmpeg",
            "-nostats",
            "-hide_banner",
            "-i",
            str(path),
            "-filter_complex",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
            timeout=60,
        )
        if code != 0:
            self.log.warning("lufs measure failed", path=str(path), code=code)
            return None
        match = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", error)
        return float(match.group(1)) if match else None

    async def _ensure_hot_copy(self, cold_path: Path) -> Path:
        # Пишем через tmp + replace, чтобы Liquidsoap не увидел недокопированный файл.
        hot_path = self.config.paths.cache_hot / cold_path.name
        hot_path.parent.mkdir(parents=True, exist_ok=True)
        if hot_path.exists():
            os.utime(hot_path, None)
            await self._enforce_hot_count()
            return hot_path

        temp_path = hot_path.with_suffix(hot_path.suffix + ".tmp")
        with contextlib.suppress(FileNotFoundError):
            temp_path.unlink()
        shutil.copy2(cold_path, temp_path)
        os.replace(temp_path, hot_path)
        os.utime(hot_path, None)
        await self._enforce_hot_count()
        return hot_path

    async def _refresh_hot_cache(self) -> None:
        # Hot - это не отдельная очередь, а короткий рабочий набор для Liquidsoap.
        # Даже если новых скачиваний в этом tick не было, поднимаем туда свежие
        # cold-файлы после рестарта pod или ручной чистки cache/hot.
        limit = max(0, self.config.prefetch.hot_max_items)
        if limit == 0:
            return
        cold_files = list(reversed(_files_by_mtime(self.config.paths.cache_cold)))
        for path, _mtime, _size in cold_files[:limit]:
            await self._ensure_hot_copy(path)

    async def _cleanup_non_audio_cache(self) -> None:
        # Liquidsoap читает директории как playlist, поэтому рядом с музыкой не
        # должны лежать .json/.webm/.tmp: он будет пытаться декодировать их как треки.
        for directory in (self.config.paths.cache_cold, self.config.paths.cache_hot):
            for path in iterate_files(directory):
                if path.suffix.lower() in AUDIO_SUFFIXES:
                    continue
                with SuppressTask():
                    path.unlink()

    async def _enforce_cold_quota(self) -> None:
        # Если PVC под холодный кеш переполнен, удаляем самые старые файлы.
        files = _files_by_mtime(self.config.paths.cache_cold)
        total = sum(size for _path, _mtime, size in files)
        for path, _mtime, size in files:
            if total <= self.config.prefetch.cold_quota_bytes:
                break
            with SuppressTask():
                path.unlink()
            total -= size

    async def _enforce_hot_count(self) -> None:
        # Горячий кеш держим коротким, иначе Liquidsoap будет слишком долго гулять
        # по старому рабочему набору.
        files = _files_by_mtime(self.config.paths.cache_hot)
        overflow = len(files) - self.config.prefetch.hot_max_items
        for index in range(max(0, overflow)):
            with SuppressTask():
                files[index][0].unlink()

    def _ensure_dirs(self) -> None:
        for path in (
            self.config.paths.cache_cold,
            self.config.paths.cache_hot,
            self.config.paths.cache_blacklist.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _files_by_mtime(directory: Path) -> list[tuple[Path, float, int]]:
    # Общий helper для LRU-очистки: сначала старые файлы.
    files: list[tuple[Path, float, int]] = []
    for path in iterate_files(directory):
        try:
            stat = path.stat()
            files.append((path, stat.st_mtime, stat.st_size))
        except OSError:
            continue
    files.sort(key=lambda item: item[1])
    return files
