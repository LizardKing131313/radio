from __future__ import annotations

import socket
from dataclasses import dataclass


class LiquidsoapTelnetError(RuntimeError):
    """Liquidsoap telnet не ответил или вернул ошибку."""


@dataclass(frozen=True)
class LiquidsoapTelnetClient:
    host: str = "127.0.0.1"
    port: int = 1234
    timeout_sec: float = 2.0

    def command(self, command: str) -> str:
        # Telnet API Liquidsoap отвечает блоком текста и строкой END.
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout_sec
            ) as connection:
                connection.settimeout(self.timeout_sec)
                connection.sendall(f"{command}\r\n".encode())
                return _read_response(connection)
        except OSError as exception:
            raise LiquidsoapTelnetError(str(exception)) from exception

    def push_request(self, uri: str) -> str:
        return self.command(f"request_queue.push {uri}")

    def push_play_now(self, uri: str) -> str:
        return self.command(f"play_now.push {uri}")

    def skip_output(self) -> str:
        # output.file.skip есть у WAV output, но playlist sources требуют своих skip-команд.
        return self.command("output.file.skip")

    def skip_request_queue(self) -> str:
        return self.command("request_queue.skip")

    def skip_play_now(self) -> str:
        return self.command("play_now.skip")

    def skip_library_sources(self) -> list[str]:
        responses: list[str] = []
        errors: list[LiquidsoapTelnetError] = []
        for command in ("playlist.skip", "playlist.1.skip"):
            try:
                responses.append(self.command(command))
            except LiquidsoapTelnetError as exception:
                errors.append(exception)
        if not responses and errors:
            raise errors[0]
        return responses

    def flush_request_queue(self) -> str:
        # Нужен, когда item уже queued в Liquidsoap, но еще не начал играть.
        return self.command("request_queue.flush_and_skip")

    def flush_play_now(self) -> str:
        return self.command("play_now.flush")

    def queue_requests(self) -> str:
        return self.command("request_queue.queue")

    def play_now_status(self) -> str:
        return self.command("play_now.status")


def _read_response(connection: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\r\nEND\r\n" in chunk or b"\nEND\n" in chunk:
            break
    text = b"".join(chunks).decode("utf-8", errors="replace")
    body = text.replace("\r\nEND\r\n", "").replace("\nEND\n", "").strip()
    if body.startswith("ERROR:"):
        raise LiquidsoapTelnetError(body)
    return body
