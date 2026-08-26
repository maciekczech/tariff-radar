from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from tariff_radar.sources import Source
from tariff_radar.storage import EventStore


@dataclass
class SyncResult:
    fetched: int = 0
    inserted: int = 0
    errors: dict[str, str] = field(default_factory=dict)


async def sync_sources(store: EventStore, sources: list[Source]) -> SyncResult:
    result = SyncResult()
    outcomes = await asyncio.gather(*(source.fetch() for source in sources), return_exceptions=True)
    for source, outcome in zip(sources, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            result.errors[source.name] = f"{type(outcome).__name__}: {outcome}"
            continue
        events = list(outcome)
        result.fetched += len(events)
        try:
            result.inserted += store.upsert_many(events)
        except Exception as exc:
            result.errors[source.name] = f"{type(exc).__name__}: {exc}"
    return result
