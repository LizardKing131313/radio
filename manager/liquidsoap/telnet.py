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
        self.config = config or get_settings()
        self.connect_timeout_sec: float = self.config.liquidsoap.connect_timeout_sec
        self.command_timeout_sec: float = self.config.liquidsoap.command_timeout_sec
        self.per_line_timeout_sec: float = self.config.liquidsoap.per_line_timeout_sec
        self.max_lines: int = self.config.liquidsoap.max_lines
        self.max_total_bytes: int = self.config.liquidsoap.max_total_bytes
        self.host: str = self.config.liquidsoap.telnet_host
        self.port: int = self.config.liquidsoap.telnet_port

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.connect_timeout_sec,
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
            while len(lines) < self.max_lines and total < self.max_total_bytes:
                line = await asyncio.wait_for(reader.readline(), timeout=self.per_line_timeout_sec)
                if not line:
                    break
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

    # ----- sugar methods -----

    async def version(self) -> ControlResult:
        return await self.command("version")

    async def help(self) -> ControlResult:
        return await self.command("help")

    async def skip(self) -> ControlResult:
        return await self.command("request.skip")

    async def push(self, uri: str) -> ControlResult:
        return await self.command(f"request.push {uri}")

    async def vars(self) -> ControlResult:
        return await self.command("vars")
