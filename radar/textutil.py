"""Date, text and money helpers. Standard library only, no model in the loop."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
HTML_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'",
    "&apos;": "'", "&nbsp;": " ", "&rsquo;": "'", "&lsquo;": "'",
    "&ldquo;": '"', "&rdquo;": '"', "&ndash;": "-", "&mdash;": "-",
}


def strip_html(value: str, limit: int = 400) -> str:
    """HTML to a single readable line."""
    if not value:
        return ""
    text = TAG_RE.sub(" ", value)
    for entity, char in HTML_ENTITIES.items():
        text = text.replace(entity, char)
    text = WS_RE.sub(" ", text).strip()
    return text[:limit].strip()


def to_iso(value: Optional[str]) -> Optional[str]:
    """Best-effort conversion of an RSS or ISO timestamp to `YYYY-MM-DD` (UTC)."""
    if not value:
        return None
    raw = value.strip()
    # RFC 822, what RSS actually uses.
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    # ISO 8601, including the "+01:00" form some feeds use.
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except ValueError:
        pass
    return parse_loose_date(raw)


def parse_loose_date(text: str) -> Optional[str]:
    """Pull a date out of prose: '30 November 2026', '30 Nov 2026', '2026-11-30'."""
    if not text:
        return None
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        return iso.group(0)
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(20\d{2})\b", text)
    if m and m.group(2).lower() in MONTHS:
        day, month, year = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
        return _safe_iso(year, month, day)
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})\b", text)
    if m and m.group(1).lower() in MONTHS:
        month, day, year = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
        return _safe_iso(year, month, day)
    return None


def _safe_iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
    except ValueError:
        return None


SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "k": 1e3, "m": 1e6, "mn": 1e6, "bn": 1e9}

# A currency signal is required. Without one, "2026" or "3 grants" would read as money.
AMOUNT_RE = re.compile(
    r"(?P<cur>USD|EUR|GBP|CHF|JPY|CAD|AUD|SEK|NOK|DKK|[$€£])\s*"
    r"(?P<num>[\d][\d,\.]*)\s*"
    r"(?P<scale>thousand|million|billion|k|m|mn|bn)?\b",
    re.IGNORECASE,
)
SYMBOL_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}
CODE_CURRENCY = {"USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK"}


def parse_amount(text: str) -> tuple[Optional[float], Optional[str]]:
    """First plausible money figure in a string, as (value, currency)."""
    if not text:
        return None, None
    for match in AMOUNT_RE.finditer(text):
        cur, digits, scale = match.group("cur"), match.group("num"), match.group("scale")
        cleaned = digits.replace(",", "")
        # 1.250.000 in some feeds means one and a quarter million.
        if cleaned.count(".") > 1:
            cleaned = cleaned.replace(".", "")
        try:
            value = float(cleaned.rstrip("."))
        except ValueError:
            continue
        if scale:
            value *= SCALES[scale.lower()]
        if value < 1000:                      # a stray figure, not a grant size
            continue
        currency = cur.upper() if cur.upper() in CODE_CURRENCY else SYMBOL_CURRENCY.get(cur)
        return value, currency
    return None, None


def days_between(deadline_iso: Optional[str], now_iso: str) -> Optional[int]:
    if not deadline_iso:
        return None
    try:
        deadline = datetime.fromisoformat(deadline_iso).date()
        now = datetime.fromisoformat(now_iso).date()
    except ValueError:
        return None
    return (deadline - now).days


def find_deadline(*texts: str) -> Optional[str]:
    """Scan prose for the phrase that names a deadline, then parse the date."""
    for text in texts:
        if not text:
            continue
        for line in re.split(r"(?<=[\.;])\s+", text):
            if re.search(r"deadline|closing date|closes on|applications? (?:are )?due|submit by", line, re.I):
                found = parse_loose_date(line)
                if found:
                    return found
    return None


def slug_tokens(text: str) -> list:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]
