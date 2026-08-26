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
            error = f"{type(outcome).__name__}: {outcome}"
            result.errors[source.name] = error
            store.record_source_run(
                source=source.name,
                status="failed",
                fetched_count=0,
                inserted_count=0,
                error=error,
            )
            continue
        events = list(outcome)
        result.fetched += len(events)
        try:
            inserted = store.upsert_many(events)
            result.inserted += inserted
            store.record_source_run(
                source=source.name,
                status="ok",
                fetched_count=len(events),
                inserted_count=inserted,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            result.errors[source.name] = error
            store.record_source_run(
                source=source.name,
                status="failed",
                fetched_count=len(events),
                inserted_count=0,
                error=error,
            )
    return result
