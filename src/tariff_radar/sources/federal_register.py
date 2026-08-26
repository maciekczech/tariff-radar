from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from tariff_radar.classify import classify_status, is_tariff_relevant
from tariff_radar.models import TariffEvent


class FederalRegisterSource:
    name = "US Federal Register"
    url = "https://www.federalregister.gov/api/v1/documents.json"

    async def fetch(self) -> list[TariffEvent]:
        params = {
            "per_page": "100",
            "order": "newest",
            "conditions[term]": "tariff OR customs duty OR antidumping",
            "conditions[publication_date][gte]": (datetime.now(UTC) - timedelta(days=45))
            .date()
            .isoformat(),
        }
        payloads: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(self.url, params={**params, "page": "1"})
            response.raise_for_status()
            first = response.json()
            payloads.append(first)
            total_pages = min(int(first.get("total_pages", 1)), 20)
            for page in range(2, total_pages + 1):
                response = await client.get(self.url, params={**params, "page": str(page)})
                response.raise_for_status()
                payloads.append(response.json())
        events_by_id: dict[str, TariffEvent] = {}
        for payload in payloads:
            for event in self.parse(payload):
                events_by_id[event.event_id] = event
        return list(events_by_id.values())

    def parse(self, payload: dict[str, Any]) -> list[TariffEvent]:
        events: list[TariffEvent] = []
        results = payload.get("results", [])
        if not isinstance(results, list):
            return events
        for item in results:
            if not isinstance(item, Mapping):
                continue
            try:
                title = str(item.get("title") or "")
                summary = str(item.get("abstract") or item.get("excerpts") or "")
                if not is_tariff_relevant(title, summary):
                    continue
                document_number = str(item.get("document_number") or item.get("html_url") or title)
                published = datetime.fromisoformat(str(item["publication_date"])).replace(
                    tzinfo=UTC
                )
                event = TariffEvent(
                    external_id=document_number,
                    source=self.name,
                    source_url=item["html_url"],
                    source_document_url=item.get("pdf_url"),
                    title=title,
                    summary=summary,
                    published_at=published,
                    reporter="United States",
                    measure_type=_measure_type(title, summary),
                    status=classify_status(title, summary),
                    raw=dict(item),
                )
            except (KeyError, TypeError, ValueError):
                continue
            events.append(event)
        return events


def _measure_type(title: str, summary: str) -> str:
    text = f"{title} {summary}".casefold()
    if "anti-dumping" in text or "antidumping" in text:
        return "anti_dumping"
    if "countervailing" in text:
        return "countervailing"
    if "safeguard" in text:
        return "safeguard"
    if "tariff-rate quota" in text or "tariff rate quota" in text:
        return "tariff_rate_quota"
    return "tariff_change"
