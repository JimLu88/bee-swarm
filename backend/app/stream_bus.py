from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator

from .models import StreamEvent


class StreamBus:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[StreamEvent]] = defaultdict(asyncio.Queue)

    def publish(self, event: StreamEvent) -> None:
        self._queues[event.decision_id].put_nowait(event)

    async def subscribe(self, decision_id: str) -> AsyncIterator[StreamEvent]:
        q = self._queues[decision_id]
        while True:
            yield await q.get()


bus = StreamBus()

