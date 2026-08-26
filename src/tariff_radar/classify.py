from __future__ import annotations

import re

_MEASURE_TERMS = (
    "tariff",
    "tariffs",
    "customs duty",
    "customs duties",
    "customs levy",
    "import duty",
    "import duties",
    "export duty",
    "export duties",
    "import tariff",
    "import tariffs",
    "export tariff",
    "export tariffs",
    "tariff-rate quota",
    "tariff rate quota",
    "mfn rate",
    "mfn rates",
    "section 301",
    "section 232",
    "rebalancing measure",
)
_TRADE_REMEDIES = (
    "anti-dumping",
    "antidumping",
    "countervailing duty",
    "countervailing duties",
    "safeguard measure",
    "safeguard investigation",
)
_NEGATIVE_CONTEXT = (
    "pipeline tariff",
    "electric tariff",
    "utility tariff",
    "freight tariff",
    "telecommunications tariff",
    "transmission tariff",
)
_ACTIONS = re.compile(
    r"\b(impos|rais|increas|reduc|cut|suspend|remov|extend|modif|chang|abolish|"
    r"introduc|enact|implement|announc|adjust|revok|continu|allocat|establish|adopt)",
    re.I,
)
_PROCEEDINGS = re.compile(
    r"\b(initiat|investigat|determin|order|review|rescind|rescission|finding|action|"
    r"circumvention|sunset|provisional|preliminary|final)",
    re.I,
)


def is_tariff_relevant(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".casefold()
    if "unrelated to customs" in text:
        return False
    if any(term in text for term in _NEGATIVE_CONTEXT) and not any(
        term in text for term in ("customs", "import duty", "export duty", "anti-dumping")
    ):
        return False
    if any(term in text for term in _TRADE_REMEDIES):
        return bool(_ACTIONS.search(text) or _PROCEEDINGS.search(text))
    if any(term in text for term in _MEASURE_TERMS):
        return bool(_ACTIONS.search(text))
    return "tariff" in text and bool(_ACTIONS.search(text)) and "trade" in text


def classify_status(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".casefold()
    if any(term in text for term in ("revocation", "revoked", "rescission", "terminated")):
        return "revoked_or_terminated"
    if "suspens" in text:
        return "suspended"
    if "preliminary" in text or "provisional" in text:
        return "preliminary"
    if any(term in text for term in ("final", " duty order", "duties imposed", "imposes")):
        return "final"
    if any(term in text for term in ("initiation", "investigation", "inquiry")):
        return "investigation"
    if "review" in text or "consultation" in text:
        return "review"
    return "announced"
