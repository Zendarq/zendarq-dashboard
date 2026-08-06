"""News aggregation: top stories from reputable sources (RSS) + article summaries.

Sources:
- CNN    (rss.cnn.com)               — works
- BBC    (feeds.bbci.co.uk)          — works
- NBC    (feeds.nbcnews.com)         — MSNBC's feeds are 403 bot-blocked; NBC is its
                                      corporate sibling and has a working feed.

Summaries are extractive (trafilatura grabs the article's main text, we keep the
opening sentences) — no LLM key needed on the VPS.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html import unescape
from typing import Any

import feedparser
import httpx
import trafilatura

from app.config import HTTP_TIMEOUT

log = logging.getLogger(__name__)

NEWS_SOURCES = [
    # CNN's RSS (rss.cnn.com) has been frozen since 2024 — scrape the homepage instead.
    {"id": "cnn", "name": "CNN",        "kind": "html", "url": "https://www.cnn.com/"},
    {"id": "bbc", "name": "BBC",        "kind": "rss",  "url": "https://feeds.bbci.co.uk/news/rss.xml"},
    {"id": "nbc", "name": "NBC",        "kind": "rss",  "url": "https://feeds.nbcnews.com/nbcnews/public/news"},
    {"id": "nhk", "name": "NHK World",  "kind": "json", "url": "https://www3.nhk.or.jp/nhkworld/data/en/news/all.json"},
    {"id": "aj",  "name": "Al Jazeera", "kind": "rss",  "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    # Local: New Hyde Park / Nassau / Queens area. Aggregated from LI/Queens
    # outlets that expose real RSS (Google News RSS redirects can't be resolved
    # to article URLs anymore, so their popup summaries would fail).
    {"id": "local", "name": "Local", "kind": "multi", "urls": [
        "https://www.longislandpress.com/feed/",
        "https://qns.com/feed/",
        "https://www.amny.com/feed/",
    ]},
]

NEWS_LIMIT = 10
NEWS_REFRESH_SECONDS = 30 * 60
SUMMARY_MAX_CHARS = 600

# Domains the summary endpoint may fetch (SSRF guard)
ALLOWED_NEWS_DOMAINS = (
    "cnn.com", "bbc.co.uk", "bbc.com", "nbcnews.com", "msnbc.com", "nhk.or.jp",
    "aljazeera.com", "longislandpress.com", "qns.com", "amny.com",
)

# In-memory cache: {source_id: [item, ...]}
_cache: dict[str, Any] = {"items": {}, "fetched_at": None}


def _fetch_rss(src: dict[str, str]) -> list[dict[str, str]]:
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (zendarq-dashboard)"}) as client:
        resp = client.get(src["url"])
        resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    stories = []
    seen_links: set[str] = set()
    for entry in feed.entries[:NEWS_LIMIT]:
        title = (entry.get("title") or "").strip()
        link = entry.get("link") or ""
        if title and link and link not in seen_links:
            seen_links.add(link)
            stories.append({
                "title": title,
                "link": link,
                "published": (entry.get("published") or entry.get("updated") or ""),
            })
    return stories


def _fetch_json(src: dict[str, str]) -> list[dict[str, str]]:
    """NHK World exposes its news as a JSON API rather than RSS."""
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (zendarq-dashboard)"}) as client:
        resp = client.get(src["url"])
        resp.raise_for_status()
    data = resp.json()
    stories = []
    for story in data.get("data", [])[:NEWS_LIMIT]:
        title = (story.get("title") or "").strip()
        page_url = story.get("page_url") or ""
        if not title or not page_url:
            continue
        stories.append({
            "title": title,
            "link": "https://www3.nhk.or.jp" + page_url,
            "published": story.get("public_at", "") or "",
        })
    return stories


def _fetch_html(src: dict[str, str]) -> list[dict[str, str]]:
    """Scrape article headlines from a server-rendered homepage (CNN)."""
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}) as client:
        resp = client.get(src["url"])
        resp.raise_for_status()
    stories = []
    seen_titles: set[str] = set()
    seen_links: set[str] = set()
    pattern = re.compile(r'href="(/20\d\d/\d\d/\d\d/[^"]+)"[^>]*>(.*?)</a>', re.S)
    junk_tags = ("<img", "<picture", "<svg", "<script", "<video", "<source")
    for href, body in pattern.findall(resp.text):
        if any(tag in body for tag in junk_tags):
            continue  # photo/video cards leak image credits into the title
        title = unescape(re.sub(r"<[^>]+>", " ", body))
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(r"^Live Updates (?:a|\d+) min(?:ute)?s? ago\s*", "", title)
        title = re.sub(r"^CNN Investigates for Subscribers\s*", "", title)
        title = re.sub(r"\s+Show all$", "", title)
        title = re.sub(r"\s+\d+:\d+$", "", title)  # video duration badge
        if len(title) < 30 or len(title) > 160 or title in seen_titles or href in seen_links:
            continue
        if "function " in title or "imageLoadError" in title:
            continue
        seen_titles.add(title)
        seen_links.add(href)
        stories.append({
            "title": title,
            "link": "https://www.cnn.com" + href,
            "published": "",
        })
        if len(stories) >= NEWS_LIMIT:
            break
    return stories


def _fetch_multi(src: dict[str, Any]) -> list[dict[str, str]]:
    """Aggregate several RSS feeds into one list, newest first, deduped.

    Items from domains outside ALLOWED_NEWS_DOMAINS are dropped so every
    story in the tab can actually get a popup summary.
    """
    from email.utils import parsedate_to_datetime
    from urllib.parse import urlparse

    def allowed(link: str) -> bool:
        host = (urlparse(link).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in ALLOWED_NEWS_DOMAINS)

    stories: list[dict[str, str]] = []
    seen_links: set[str] = set()
    for url in src["urls"]:
        sub = {k: v for k, v in src.items() if k != "urls"}
        sub["url"] = url
        for story in _fetch_rss(sub):
            if story["link"] not in seen_links and allowed(story["link"]):
                seen_links.add(story["link"])
                stories.append(story)

    def pub_ts(s: dict[str, str]) -> float:
        try:
            dt = parsedate_to_datetime(s["published"]) if s["published"] else None
            return dt.timestamp() if dt else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    stories.sort(key=pub_ts, reverse=True)
    return stories[:NEWS_LIMIT]


def fetch_feeds() -> None:
    """Parse all feeds and store the top N items per source in _cache."""
    items: dict[str, list[dict[str, str]]] = {}
    for src in NEWS_SOURCES:
        try:
            kind = src.get("kind", "rss")
            if kind == "json":
                items[src["id"]] = _fetch_json(src)
            elif kind == "html":
                items[src["id"]] = _fetch_html(src)
            elif kind == "multi":
                items[src["id"]] = _fetch_multi(src)
            else:
                items[src["id"]] = _fetch_rss(src)
            log.info("news: %s -> %d stories", src["id"], len(items[src["id"]]))
        except Exception:  # noqa: BLE001
            log.exception("news feed failed for %s", src["id"])
            items[src["id"]] = []
    _cache["items"] = items
    _cache["fetched_at"] = datetime.now().isoformat(timespec="seconds")


def get_cache() -> dict[str, Any]:
    return {
        "sources": NEWS_SOURCES,
        "items": _cache["items"],
        "fetched_at": _cache["fetched_at"],
    }


def summarize(url: str, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    """Fetch an article and return its opening text as an extractive summary."""
    with httpx.Client(
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"},
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
    extracted = trafilatura.bare_extraction(
        resp.text, include_comments=False, include_tables=False, favor_recall=False
    )
    # trafilatura >= 1.8 returns a Document object; older versions return a dict
    text = getattr(extracted, "text", None)
    if text is None and isinstance(extracted, dict):
        text = extracted.get("text")
    text = text or ""
    if not text:
        return ""
    return " ".join(text.split())[:max_chars]
