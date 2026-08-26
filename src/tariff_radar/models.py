from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class TariffEvent(BaseModel):
    """A source-backed signal about a tariff or trade-remedy change."""

    external_id: str
    source: str
    source_url: str
    source_document_url: str | None = None
    title: str
    summary: str = ""
    published_at: datetime
    effective_from: datetime | None = None
    reporter: str | None = None
    targets: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    hs_codes: list[str] = Field(default_factory=list)
    measure_type: str = "tariff_signal"
    status: str = "announced"
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @field_validator("source_url", "source_document_url")
    @classmethod
    def http_urls_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source URLs must use HTTP(S)")
        return value

    @field_validator("published_at", "effective_from")
    @classmethod
    def normalize_to_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def event_id(self) -> str:
        return f"{self.source}:{self.external_id}"


class EventPage(BaseModel):
    total: int
    items: list[TariffEvent]
