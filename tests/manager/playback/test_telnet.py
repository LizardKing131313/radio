from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable

import pytest

from manager.playback import telnet
from manager.playback.telnet import LiquidsoapTelnetClient, LiquidsoapTelnetError


def _serve_once(response: bytes) -> tuple[int, list[str], threading.Thread]:
    commands: list[str] = []
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = int(server.getsockname()[1])

    def run() -> None:
        try:
            connection, _address = server.accept()
            with connection:
                commands.append(connection.recv(4096).decode("utf-8"))
                connection.sendall(response)
        finally:
            server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return port, commands, thread


def _with_server(response: bytes, call: Callable[[LiquidsoapTelnetClient], str]) -> str:
    port, commands, thread = _serve_once(response)
    client = LiquidsoapTelnetClient(port=port)
    result = call(client)
    thread.join(timeout=2)
    assert commands
    return result


def test_telnet_client_commands() -> None:
    assert _with_server(b"OK\r\nEND\r\n", lambda client: client.command("help")) == "OK"
    assert (
        _with_server(b"Queued\r\nEND\r\n", lambda client: client.push_request("/tmp/a.opus"))
        == "Queued"
    )
    assert (
        _with_server(b"Queued\r\nEND\r\n", lambda client: client.push_play_now("/tmp/a.opus"))
        == "Queued"
    )
    assert _with_server(b"Done.\r\nEND\r\n", lambda client: client.skip_output()) == "Done."
    assert _with_server(b"Done.\r\nEND\r\n", lambda client: client.skip_request_queue()) == "Done."
    assert _with_server(b"Done.\r\nEND\r\n", lambda client: client.skip_play_now()) == "Done."
    assert _with_server(b"Done.\r\nEND\r\n", lambda client: client.flush_request_queue()) == "Done."
    assert _with_server(b"Done.\r\nEND\r\n", lambda client: client.flush_play_now()) == "Done."
    assert _with_server(b"3\r\nEND\r\n", lambda client: client.queue_requests()) == "3"
    assert _with_server(b"playing\r\nEND\r\n", lambda client: client.play_now_status()) == "playing"


def test_skip_library_sources_calls_both_playlists(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def command(_client: LiquidsoapTelnetClient, command_name: str) -> str:
        calls.append(command_name)
        return "Done."

    monkeypatch.setattr(LiquidsoapTelnetClient, "command", command)

    assert LiquidsoapTelnetClient().skip_library_sources() == ["Done.", "Done."]
    assert calls == ["playlist.skip", "playlist.1.skip"]


def test_skip_library_sources_requires_at_least_one_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def command(_client: LiquidsoapTelnetClient, command_name: str) -> str:
        raise LiquidsoapTelnetError(f"{command_name} missing")

    monkeypatch.setattr(LiquidsoapTelnetClient, "command", command)

    with pytest.raises(LiquidsoapTelnetError, match=r"playlist\.skip missing"):
        LiquidsoapTelnetClient().skip_library_sources()


def test_telnet_error_response() -> None:
    with pytest.raises(LiquidsoapTelnetError):
        _with_server(b"ERROR: bad command\r\nEND\r\n", lambda client: client.command("bad"))


def test_telnet_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_connect(*_args: object, **_kwargs: object) -> socket.socket:
        raise OSError("closed")

    monkeypatch.setattr(telnet.socket, "create_connection", fail_connect)
    with pytest.raises(LiquidsoapTelnetError, match="closed"):
        LiquidsoapTelnetClient().command("help")


def test_read_response_handles_closed_socket() -> None:
    left, right = socket.socketpair()
    try:
        right.close()
        assert telnet._read_response(left) == ""
    finally:
        left.close()


def test_read_response_reads_multiple_chunks() -> None:
    left, right = socket.socketpair()

    def write_chunks() -> None:
        with right:
            right.sendall(b"part\r\n")
            time.sleep(0.05)
            right.sendall(b"END\r\n")

    thread = threading.Thread(target=write_chunks, daemon=True)
    thread.start()
    try:
        assert telnet._read_response(left) == "part"
    finally:
        left.close()
        thread.join(timeout=2)
