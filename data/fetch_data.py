"""Data collection helpers for energy and RSS indicators."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree


@dataclass
class Article:
    title: str
    link: str
    published: str
    summary: str


class HTTPClient:
    """Small GET-only client with JSON and text helpers."""

    @staticmethod
    def get_text(url: str, timeout: int = 20) -> str:
        with urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def get_json(url: str, params: Optional[Dict[str, str]] = None, timeout: int = 20) -> Dict:
        query = f"{url}?{urlencode(params or {})}" if params else url
        raw = HTTPClient.get_text(query, timeout=timeout)
        return json.loads(raw)


def _parse_rss_or_atom(xml_text: str) -> List[Article]:
    root = ElementTree.fromstring(xml_text)
    articles: List[Article] = []

    # RSS style
    for item in root.findall(".//item"):
        articles.append(
            Article(
                title=(item.findtext("title") or "").strip(),
                link=(item.findtext("link") or "").strip(),
                published=(item.findtext("pubDate") or "").strip(),
                summary=(item.findtext("description") or "").strip(),
            )
        )

    # Atom style
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        link = ""
        link_tag = entry.find("atom:link", ns)
        if link_tag is not None:
            link = link_tag.attrib.get("href", "")
        articles.append(
            Article(
                title=(entry.findtext("atom:title", default="", namespaces=ns) or "").strip(),
                link=link.strip(),
                published=(entry.findtext("atom:updated", default="", namespaces=ns) or "").strip(),
                summary=(entry.findtext("atom:summary", default="", namespaces=ns) or "").strip(),
            )
        )

    return articles


def fetch_fred_series(base_url: str, api_key: str, series_id: str, days: int = 14) -> List[Dict[str, str]]:
    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=days + 10)
    payload = HTTPClient.get_json(
        base_url,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_date.isoformat(),
            "observation_end": end_date.isoformat(),
        },
    )
    observations = payload.get("observations", [])
    return [row for row in observations if row.get("value") not in (".", None)]


def fetch_rss_articles(feed_url: str) -> List[Article]:
    try:
        xml_text = HTTPClient.get_text(feed_url)
        return _parse_rss_or_atom(xml_text)
    except Exception:
        return []


def keyword_mentions(articles: List[Article], keywords: List[str]) -> List[Article]:
    keyset = [k.lower() for k in keywords]
    matches = []
    for article in articles:
        text = f"{article.title} {article.summary}".lower()
        if any(k in text for k in keyset):
            matches.append(article)
    return matches
