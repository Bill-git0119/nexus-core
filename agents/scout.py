"""
The Scout Agent
Scans daily trending topics via Google Search API (SerpAPI).
Focus areas: Semiconductor/Taiwan Stock Supply Chain, Longevity/Sports Medicine.
Outputs: data/raw_topics.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = str(PROJECT_ROOT / "data" / "raw_topics.json")
STRATEGY_PATH = PROJECT_ROOT / "config" / "strategy.json"

# Default focus areas (overridden by config/strategy.json when available)
DEFAULT_FOCUS_AREAS = {
    "semiconductor": {
        "domain": "Semiconductor/Taiwan Stock Supply Chain",
        "queries": [
            "Taiwan semiconductor supply chain news today",
            "TSMC stock market latest",
            "global chip shortage update 2026",
        ],
    },
    "longevity": {
        "domain": "Longevity/Sports Medicine",
        "queries": [
            "longevity science breakthrough 2026",
            "sports medicine latest research",
            "anti-aging clinical trial results",
        ],
    },
}

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
TOPICS_PER_DOMAIN = 3


def load_focus_areas() -> list[dict]:
    """
    Build FOCUS_AREAS from config/strategy.json if it exists.
    The Architect's boost_queries are appended to base_queries for the
    prioritized domain.
    """
    areas = []

    if STRATEGY_PATH.exists():
        print(f"[Scout] Loading strategy from {STRATEGY_PATH}")
        with open(STRATEGY_PATH, "r", encoding="utf-8") as f:
            strategy = json.load(f)

        keywords = strategy.get("keywords", {})
        for key, defaults in DEFAULT_FOCUS_AREAS.items():
            kw_config = keywords.get(key, {})
            base = kw_config.get("base_queries", defaults["queries"])
            boost = kw_config.get("boost_queries", [])
            combined = base + boost
            areas.append({"domain": defaults["domain"], "queries": combined})
            if boost:
                print(f"[Scout] Strategy boost for {key}: +{len(boost)} keywords")
    else:
        print("[Scout] No strategy.json found — using default keywords")
        for defaults in DEFAULT_FOCUS_AREAS.values():
            areas.append({"domain": defaults["domain"], "queries": list(defaults["queries"])})

    return areas


# ---------------------------------------------------------------------------
# Google Search via SerpAPI
# ---------------------------------------------------------------------------
def search_google(query: str, retries: int = MAX_RETRIES) -> list[dict]:
    """Call SerpAPI and return organic results. Auto-retries on failure."""
    if not SERPAPI_KEY:
        print(f"[Scout] WARNING: SERPAPI_KEY not set. Using mock results for: {query}")
        return _mock_results(query)

    url = "https://serpapi.com/search.json"
    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "num": 5,
        "tbm": "nws",  # news tab for freshness
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("news_results", data.get("organic_results", []))
        except (requests.RequestException, ValueError) as exc:
            print(f"[Scout] Attempt {attempt}/{retries} failed for '{query}': {exc}")
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    return []


def _mock_results(query: str) -> list[dict]:
    """Fallback mock results when no API key is configured."""
    return [
        {
            "title": f"[Mock] Trending: {query}",
            "link": "https://example.com/mock-article",
            "snippet": f"Mock snippet for query '{query}'. Replace with real SERPAPI_KEY.",
            "source": "Mock Source",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    ]


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------
def extract_topics(domain: str, queries: list[str]) -> list[dict]:
    """Run queries for a domain and return top N deduplicated topics."""
    all_results = []
    for q in queries:
        print(f"[Scout] Searching: {q}")
        results = search_google(q)
        for r in results:
            all_results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                    "source": r.get("source", ""),
                    "date": r.get("date", ""),
                    "domain": domain,
                    "query": q,
                }
            )

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for item in all_results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique.append(item)

    return unique[:TOPICS_PER_DOMAIN]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> str:
    """Execute the Scout pipeline. Returns output file path."""
    print(f"[Scout] Starting scan at {datetime.now(timezone.utc).isoformat()}")

    focus_areas = load_focus_areas()

    topics: list[dict] = []
    for area in focus_areas:
        found = extract_topics(area["domain"], area["queries"])
        topics.extend(found)
        print(f"[Scout] {area['domain']}: found {len(found)} topics")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_topics": len(topics),
        "topics": topics,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[Scout] Saved {len(topics)} topics to {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    run()
