"""
Signal handlers installation utilities.

- Installs SIGINT/SIGTERM handlers using the provided callback.
- Uses contextlib.suppress(NotImplementedError) for platforms
  where add_signal_handler is not implemented (e.g., Windows).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Callable


def install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    on_signal: Callable[[signal.Signals], None],
    *,
    signals: tuple[signal.Signals, ...] = (signal.SIGINT, signal.SIGTERM),
) -> None:
    """Register OS signal handlers that call `on_signal(signal)`."""
    for sig in signals:
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, on_signal, sig)
