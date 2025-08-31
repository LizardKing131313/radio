from __future__ import annotations

from collections import OrderedDict


class LRUSet:
    """O(1) membership + eviction by capacity using OrderedDict."""

    __slots__ = ("_capacity", "_data")

    def __init__(self, capacity: int) -> None:
        self._data: OrderedDict[str, None] = OrderedDict()
        self._capacity: int = max(1, int(capacity))

    def add(self, key: str) -> None:
        if key in self._data:
            self._data.move_to_end(key, last=True)
            return
        self._data[key] = None
        if len(self._data) > self._capacity:
            self._data.popitem(last=False)

    def __contains__(self, key: str) -> bool:  # pragma: no cover - trivial
        if key in self._data:
            self._data.move_to_end(key, last=True)
            return True
        return False

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._data)
