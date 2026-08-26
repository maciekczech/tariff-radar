from __future__ import annotations

import calendar
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from tariff_radar.classify import is_tariff_relevant
from tariff_radar.models import TariffEvent


class RssSource:
    def __init__(self, name: str, url: str, reporter: str | None) -> None:
        self.name = name
        self.url = url
        self.reporter = reporter

    async def fetch(self) -> list[TariffEvent]:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(self.url)
            response.raise_for_status()
        return self.parse(response.content)

    def parse(self, content: bytes) -> list[TariffEvent]:
        feed = feedparser.parse(content)
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
    return datetime.now(UTC)


def _strip_html(value: str) -> str:
    import re
    from html import unescape

    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())
