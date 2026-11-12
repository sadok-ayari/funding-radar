"""Source adapters.

Three shapes cover most funders:
  * `rss`      — an RSS or Atom feed (the cheapest, most stable option)
  * `ted`      — the EU Tenders Electronic Daily search API (JSON POST)
  * `html_list`— a plain HTML page of calls, driven by a regex in the config

Adding a funder means adding a block to `config/sources.json`, not touching the
pipeline. Write a new adapter only when a source has no feed and no API.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from . import http
from .models import Opportunity
from .textutil import find_deadline, parse_amount, strip_html, to_iso


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def _child_text(node: ET.Element, *names: str) -> str:
    for child in node:
        if _localname(child.tag) in names:
            return (child.text or "").strip()
    return ""


def _children(node: ET.Element, *names: str) -> List[str]:
    out = []
    for child in node:
        if _localname(child.tag) in names:
            text = (child.text or "").strip()
            if text:
                out.append(text)
    return out


class Adapter:
    type = "base"

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.name = cfg.get("name") or cfg.get("url", "unnamed")
        self.tier = int(cfg.get("tier", 3))
        self.limit = int(cfg.get("limit", 50))

    def fetch(self, **http_kwargs: Any) -> List[Opportunity]:
        raise NotImplementedError

    # -- shared helpers ---------------------------------------------------
    def _build(self, title: str, url: str, summary: str = "", published: Optional[str] = None,
               tags: Optional[List[str]] = None, funder: Optional[str] = None,
               country: Optional[str] = None, raw_id: Optional[str] = None) -> Opportunity:
        prose = f"{title}. {summary}"
        amount, currency = parse_amount(prose)
        return Opportunity(
            source=self.name,
            source_tier=self.tier,
            title=strip_html(title, limit=300),
            url=url,
            published=to_iso(published),
            deadline=find_deadline(summary, title),
            amount=amount,
            currency=currency,
            summary=strip_html(summary, limit=400),
            tags=list(dict.fromkeys(tags or [])),
            funder=funder,
            country=country,
            raw_id=raw_id,
        )


class RSSAdapter(Adapter):
    type = "rss"

    def fetch(self, **http_kwargs: Any) -> List[Opportunity]:
        body = http.request(self.cfg["url"], **http_kwargs)
        return self.parse(body)

    def parse(self, body: str) -> List[Opportunity]:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as error:
            raise http.FetchError(f"{self.name}: feed is not valid XML ({error})")
        nodes = [n for n in root.iter() if _localname(n.tag) in ("item", "entry")]
        out: List[Opportunity] = []
        for node in nodes[: self.limit]:
            title = _child_text(node, "title")
            link = _child_text(node, "link")
            if not link:
                for child in node:
                    if _localname(child.tag) == "link":
                        link = child.attrib.get("href", "")
                        if link:
                            break
            summary = _child_text(node, "description", "summary", "content")
            published = _child_text(node, "pubdate", "published", "updated", "date")
            categories = _children(node, "category", "subject")
            if not title or not link:
                continue
            out.append(self._build(title, link, summary, published, categories,
                                   raw_id=_child_text(node, "guid", "id")))
        return out


class TEDAdapter(Adapter):
    """EU Tenders Electronic Daily — procurement rather than grants, tier 3."""

    type = "ted"
    ENDPOINT = "https://api.ted.europa.eu/v3/notices/search"
    FIELDS = [
        "publication-number", "notice-title", "buyer-country", "buyer-name",
        "publication-date", "deadline-receipt-tender-date-lot",
        "classification-cpv", "estimated-value-lot",
    ]

    def fetch(self, **http_kwargs: Any) -> List[Opportunity]:
        payload = json.dumps({
            "query": self.cfg.get("query", "publication-date>=today(-7)"),
            "page": 1,
            "limit": self.limit,
            "fields": self.FIELDS,
        }).encode("utf-8")
        body = http.request(
            self.ENDPOINT,
            method="POST",
            body=payload,
            headers={"Content-Type": "application/json"},
            **http_kwargs,
        )
        return self.parse(body)

    @staticmethod
    def _first(value: Any, prefer: str = "eng") -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and value:
            if prefer in value:
                picked = value[prefer]
                return picked[0] if isinstance(picked, list) and picked else str(picked)
            first = next(iter(value.values()))
            if isinstance(first, list):
                return first[0] if first else ""
            return str(first)
        return ""

    def parse(self, body: str) -> List[Opportunity]:
        try:
            data = json.loads(body)
        except json.JSONDecodeError as error:
            raise http.FetchError(f"{self.name}: response is not JSON ({error})")
        if "notices" not in data:
            message = data.get("message", "no notices key in response")
            raise http.FetchError(f"{self.name}: {message}")
        out: List[Opportunity] = []
        prefixes = [str(p) for p in self.cfg.get("cpv_prefixes", [])]
        for notice in data["notices"][: self.limit]:
            number = notice.get("publication-number", "")
            title = self._first(notice.get("notice-title"))
            if not number or not title:
                continue
            cpv = [str(code) for code in notice.get("classification-cpv", [])]
            if prefixes and not any(code.startswith(tuple(prefixes)) for code in cpv):
                continue
            links = notice.get("links", {})
            url = (links.get("xml", {}).get("MUL")
                   or links.get("pdf", {}).get("ENG")
                   or f"https://ted.europa.eu/en/notice/{number}")
            values = [float(v) for v in notice.get("estimated-value-lot", []) if _is_number(v)]
            countries = notice.get("buyer-country") or []
            opp = self._build(
                title, url,
                summary=f"EU procurement notice {number}",
                published=notice.get("publication-date"),
                tags=notice.get("classification-cpv", []),
                funder=self._first(notice.get("buyer-name")),
                country=countries[0] if countries else None,
                raw_id=number,
            )
            if values:
                opp.amount, opp.currency = max(values), "EUR"
            out.append(opp)
        return out


class HtmlListAdapter(Adapter):
    """Last resort: a regex over the page. Prefer a feed whenever one exists."""

    type = "html_list"

    def fetch(self, **http_kwargs: Any) -> List[Opportunity]:
        body = http.request(self.cfg["url"], **http_kwargs)
        return self.parse(body)

    def parse(self, body: str) -> List[Opportunity]:
        pattern = self.cfg.get("link_pattern")
        if not pattern:
            raise http.FetchError(f"{self.name}: html_list source needs a link_pattern")
        out: List[Opportunity] = []
        seen = set()
        for match in re.finditer(pattern, body, re.I | re.S):
            href = match.group("href") if "href" in match.groupdict() else match.group(1)
            title = match.group("text") if "text" in match.groupdict() else match.group(2)
            title = strip_html(title, 300)
            url = urljoin(self.cfg["url"], href.strip())
            if not title or url in seen:
                continue
            seen.add(url)
            out.append(self._build(title, url, summary="", tags=self.cfg.get("tags")))
            if len(out) >= self.limit:
                break
        return out


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


ADAPTERS = {"rss": RSSAdapter, "ted": TEDAdapter, "html_list": HtmlListAdapter}


def build(cfg: Dict[str, Any]) -> Adapter:
    kind = cfg.get("type", "rss")
    if kind not in ADAPTERS:
        raise ValueError(f"unknown source type '{kind}' for {cfg.get('name')}")
    return ADAPTERS[kind](cfg)
