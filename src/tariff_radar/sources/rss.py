from __future__ import annotations

import asyncio
import calendar
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from tariff_radar.classify import classify_status, is_tariff_relevant
from tariff_radar.models import TariffEvent


class RssSource:
    def __init__(self, name: str, url: str, reporter: str | None) -> None:
        self.name = name
        self.url = url
        self.reporter = reporter

    async def fetch(self) -> list[TariffEvent]:
        headers = {"User-Agent": "TariffRadar/0.1 (+https://github.com/maciekczech/tariff-radar)"}
        async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers=headers) as client:
            for attempt in range(3):
                try:
                    response = await client.get(self.url)
                    response.raise_for_status()
                    return self.parse(response.content)
                except (httpx.TransportError, httpx.HTTPStatusError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError("RSS retry loop ended unexpectedly")

    def parse(self, content: bytes) -> list[TariffEvent]:
        feed = feedparser.parse(content)
        if feed.bozo and not feed.entries:
            raise ValueError("unreadable RSS feed")
        events: list[TariffEvent] = []
        for entry in feed.entries:
            try:
                title = str(entry.get("title", ""))
                summary = str(entry.get("summary", entry.get("description", "")))
                if not is_tariff_relevant(title, summary):
                    continue
                link = str(entry.get("link", self.url))
                external_id = str(entry.get("id", link))
                event = TariffEvent(
                    external_id=external_id,
                    source=self.name,
                    source_url=link,
                    title=title,
                    summary=_strip_html(summary),
                    published_at=_entry_datetime(entry),
                    reporter=self.reporter,
                    status=classify_status(title, summary),
                    raw=dict(entry),
                )
            except (TypeError, ValueError):
                continue
            events.append(event)
        return events


def _entry_datetime(entry: dict[str, Any]) -> datetime:
    for key in ("published", "updated"):
        value = entry.get(key)
        if value:
            parsed = parsedate_to_datetime(str(value))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
    raise ValueError("RSS entry has no publication date")


def _strip_html(value: str) -> str:
    import re
    from html import unescape

    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())
