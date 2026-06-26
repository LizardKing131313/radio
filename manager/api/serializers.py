from __future__ import annotations

from manager.track_queue.models import QueueItem, Track


def queue_entry(item: tuple[QueueItem, Track]) -> dict[str, object]:
    queue_item, track = item
    return {"queue_item": dict(queue_item.to_dict()), "track": dict(track.to_dict())}
