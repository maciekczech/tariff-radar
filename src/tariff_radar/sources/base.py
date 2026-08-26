from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from tariff_radar.models import TariffEvent


class Source(Protocol):
    name: str
    url: str

    async def fetch(self) -> Sequence[TariffEvent]: ...
