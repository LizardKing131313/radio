from __future__ import annotations

import asyncio
import contextlib

from manager.config import AppConfig, get_settings
from manager.runner.control import ControlResult, Error, Success


class Telnet:
    """Liquidsoap telnet-like client.

    Особенности:
      - после коннекта сразу посылаем CRLF ("пинок");
      - каждая команда завершается CRLF;
      - читаем строки до маркера END.
    """

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_settings()
        self._settings = self._config.liquidsoap

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._settings.telnet_host, self._settings.telnet_port),
            timeout=self._settings.connect_timeout_sec,
        )
        return reader, writer

    async def connect_only(self) -> ControlResult:
        """Just check TCP connect works."""
        writer: asyncio.StreamWriter | None = None
        try:
            _, writer = await self._open()
        except asyncio.TimeoutError:  # noqa: UP041
            return Error("connect timeout")
        except OSError as exc:
            return Error(f"connect error: {exc!r}")
        finally:
            if writer is not None:
                with contextlib.suppress(Exception):
                    writer.close()
                    await writer.wait_closed()
        return Success("connected")

    async def command(self, cmd: str) -> ControlResult:
        """Send command and collect response until END marker."""
        try:
            reader, writer = await self._open()
        except asyncio.TimeoutError:  # noqa: UP041
            return Error("connect timeout")
        except OSError as exc:
            return Error(f"connect error: {exc!r}")

        try:
            # wake-up ping
            writer.write(b"\r\n")
            await writer.drain()
            await asyncio.sleep(0.05)

            if not cmd.endswith("\r\n"):
                cmd = cmd + "\r\n"
            writer.write(cmd.encode())
            await writer.drain()

            total = 0
            lines: list[str] = []
            while len(lines) < self._settings.max_lines and total < self._settings.max_total_bytes:
                # noinspection PyUnresolvedReferences
                line = await asyncio.wait_for(
                    reader.readline(), timeout=self._settings.per_line_timeout_sec
                )
                if not line:
                    break
                # noinspection PyUnresolvedReferences
                s = line.decode(errors="replace").rstrip("\r\n")
                if s == "END":
                    break
                total += len(line)
                lines.append(s)

            if not lines:
                return Error("empty response")
            return Success("\n".join(lines))
        except asyncio.TimeoutError:  # noqa: UP041
            return Error("read/write timeout")
        except (BrokenPipeError, ConnectionResetError):
            return Error("connection closed")
        except Exception as exc:
            return Error(f"io error: {exc!r}")
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def help(self) -> ControlResult:
        return await self.command("help")

    async def version(self) -> ControlResult:
        return await self.command("version")

    async def uptime(self) -> ControlResult:
        return await self.command("uptime")

    async def cold_next(self) -> ControlResult:
        return await self.command("cold.next")

    async def cold_reload(self) -> ControlResult:
        return await self.command("cold.reload")

    async def cold_skip(self) -> ControlResult:
        return await self.command("cold.skip")

    async def cold_url(self, uri: str) -> ControlResult:
        return await self.command(f"cold.uri {uri}")

    async def hot_next(self) -> ControlResult:
        return await self.command("hot.next")

    async def hot_reload(self) -> ControlResult:
        return await self.command("hot.reload")

    async def hot_skip(self) -> ControlResult:
        return await self.command("hot.skip")

    async def hot_uri(self, uri: str) -> ControlResult:
        return await self.command(f"hot.uri {uri}")

    async def output_file_metadata(self) -> ControlResult:
        return await self.command("output_file.metadata")

    async def output_file_remaining(self) -> ControlResult:
        return await self.command("output_file.remaining")

    async def output_file_skip(self) -> ControlResult:
        return await self.command("output_file.skip")

    async def request_alive(self) -> ControlResult:
        return await self.command("request.alive")

    async def request_all(self) -> ControlResult:
        return await self.command("request.all")

    async def request_metadata(self, rid: str) -> ControlResult:
        return await self.command(f"request.metadata {rid}")

    async def request_on_air(self) -> ControlResult:
        return await self.command("request.on_air")

    async def request_resolving(self) -> ControlResult:
        return await self.command("request.resolving")

    async def request_trace(self, rid: str) -> ControlResult:
        return await self.command(f"request.trace {rid}")

    async def rq_flush_and_skip(self) -> ControlResult:
        return await self.command("rq.flush_and_skip")

    async def rq_push(self, uri: str) -> ControlResult:
        return await self.command(f"rq.push {uri}")

    async def rq_queue(self) -> ControlResult:
        return await self.command("rq.queue")

    async def rq_skip(self) -> ControlResult:
        return await self.command("rq.skip")
