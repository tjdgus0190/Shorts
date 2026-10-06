"""Google 트렌드 '실시간 인기 검색어' RSS 수집 (무료, 키 불필요)."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

log = logging.getLogger(__name__)

RSS_URL = "https://trends.google.com/trending/rss?geo={geo}"
NS = {"ht": "https://trends.google.com/trending/rss"}


def parse_traffic(text: str) -> int:
    """'2,000+' / '1만+' / '500+' 같은 표기를 정수로."""
    text = (text or "").replace(",", "").replace("+", "").strip()
    m = re.match(r"([\d.]+)\s*(만|천|K|M)?", text, re.I)
    if not m:
        return 0
    n = float(m.group(1))
    mult = {"만": 10_000, "천": 1_000, "k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return int(n * mult)


def parse_rss(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        news = [
            {
                "title": (n.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip(),
                "source": (n.findtext("ht:news_item_source", default="", namespaces=NS) or "").strip(),
                "url": (n.findtext("ht:news_item_url", default="", namespaces=NS) or "").strip(),
            }
            for n in item.findall("ht:news_item", NS)
        ]
        traffic_raw = item.findtext("ht:approx_traffic", default="", namespaces=NS)
        items.append({
            "keyword": (item.findtext("title") or "").strip(),
            "traffic": traffic_raw,
            "traffic_num": parse_traffic(traffic_raw),
            "picture": item.findtext("ht:picture", default="", namespaces=NS),
            "news": news,
        })
    items.sort(key=lambda x: x["traffic_num"], reverse=True)
    return items


def fetch_trends(geo: str = "KR", timeout: int = 20) -> list[dict]:
    r = requests.get(RSS_URL.format(geo=geo), timeout=timeout,
                     headers={"User-Agent": "Mozilla/5.0 (shorts-bot)"})
    r.raise_for_status()
    return parse_rss(r.text)


def is_sensitive(trend: dict, blocked: list[str]) -> str | None:
    """사건·사고·정치 등 민감 키워드가 포함되면 해당 단어를 반환."""
    haystack = " ".join([trend["keyword"], *(n["title"] for n in trend.get("news", []))])
    for word in blocked:
        if word in haystack:
            return word
    return None
