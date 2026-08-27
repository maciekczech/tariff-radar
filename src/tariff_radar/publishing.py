from __future__ import annotations

import re
from datetime import datetime

from tariff_radar.models import TariffEvent

_X_LIMIT = 280
_X_URL_WEIGHT = 23
_URL_RE = re.compile(r"https?://\S+")
_STATUS_ICON = {
    "final": "✅",
    "preliminary": "🟡",
    "investigation": "🔎",
    "review": "📋",
    "suspended": "⏸️",
    "revoked_or_terminated": "🛑",
}


def build_x_thread(
    events: list[TariffEvent],
    *,
    generated_at: datetime,
    max_items: int = 5,
    detected_total: int | None = None,
) -> list[str]:
    """Build a compact X thread. No network or account access occurs here."""
    selected = events[:max_items]
    signal_count = len(events) if detected_total is None else detected_total
    if not selected:
        return [
            _numbered(
                "Tariff Radar — daily brief\n"
                f"{generated_at:%d %b %Y}\n\n"
                "No new official tariff signals in the last 24 hours.",
                1,
                1,
            )
        ]

    total = len(selected) + 1
    posts = [
        _numbered(
            "Tariff Radar — daily brief\n"
            f"{generated_at:%d %b %Y}\n\n"
            f"{signal_count} official signal(s) detected. "
            "Source-backed links follow; stages are not treated as equivalent.",
            1,
            total,
        )
    ]
    for position, event in enumerate(selected, start=2):
        icon = _STATUS_ICON.get(event.status, "📡")
        actor = _truncate_weighted(
            _neutralize_mentions(event.reporter or "Multiple / unspecified"), 60
        )
        footer = f"\n{event.source_url}\n\n{position}/{total}"
        metadata = f"\n{actor} · {event.status.replace('_', ' ')}"
        fixed = f"{icon} {metadata}{footer}"
        title_budget = max(_X_LIMIT - x_weighted_length(fixed), 20)
        title = _truncate_weighted(_neutralize_mentions(event.title), title_budget)
        post = f"{icon} {title}{metadata}{footer}"
        if x_weighted_length(post) > _X_LIMIT:
            raise ValueError("X post cannot fit within the weighted 280-character limit")
        posts.append(post)
    return posts


def x_weighted_length(text: str) -> int:
    """Conservative X length: URLs weigh 23, non-ASCII code points weigh 2."""
    total = 0
    cursor = 0
    for match in _URL_RE.finditer(text):
        total += _plain_weight(text[cursor : match.start()]) + _X_URL_WEIGHT
        cursor = match.end()
    return total + _plain_weight(text[cursor:])


def _plain_weight(text: str) -> int:
    return sum(1 if ord(character) < 128 else 2 for character in text)


def _neutralize_mentions(text: str) -> str:
    return text.replace("@", "@\u200b")


def _numbered(text: str, position: int, total: int) -> str:
    suffix = f"\n\n{position}/{total}"
    body = _truncate_weighted(text, _X_LIMIT - x_weighted_length(suffix))
    return f"{body}{suffix}"


def _truncate_weighted(text: str, limit: int) -> str:
    compact = " ".join(text.split()) if "\n" not in text else text.strip()
    if x_weighted_length(compact) <= limit:
        return compact
    ellipsis = "…"
    available = max(limit - x_weighted_length(ellipsis), 0)
    result: list[str] = []
    weight = 0
    for character in compact:
        character_weight = _plain_weight(character)
        if weight + character_weight > available:
            break
        result.append(character)
        weight += character_weight
    return "".join(result).rstrip() + ellipsis
