"""
The Critic Agent
Fact-checks Scout output against original sources.
Discards unverified or 6+ months old news.
Outputs: verified_data.json (project root)
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOUT_INPUT = os.path.join(PROJECT_ROOT, "data", "raw_topics.json")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "verified_data.json")

MAX_RETRIES = 3
RETRY_DELAY = 5
FRESHNESS_MONTHS = 6


# ---------------------------------------------------------------------------
# Date validation
# ---------------------------------------------------------------------------
def parse_date(date_str: str) -> datetime | None:
    """Try multiple date formats, return datetime or None."""
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def is_fresh(date_str: str) -> bool:
    """Return True if the article is less than 6 months old."""
    dt = parse_date(date_str)
    if dt is None:
        return False  # unverifiable date → discard
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * FRESHNESS_MONTHS)
    return dt >= cutoff


# ---------------------------------------------------------------------------
# Source verification via SerpAPI
# ---------------------------------------------------------------------------
def verify_against_source(topic: dict, retries: int = MAX_RETRIES) -> dict | None:
    """
    Cross-reference a topic by searching for its title.
    Returns enriched topic dict if verified, None otherwise.
    """
    title = topic.get("title", "")
    original_url = topic.get("url", "")

    if not title:
        return None

    # --- Freshness check ---
    date_str = topic.get("date", "")
    if date_str and not is_fresh(date_str):
        print(f"[Critic] DISCARDED (stale >6mo): {title}")
        return None

    # --- Cross-reference search ---
    corroborating_sources = _cross_search(title, retries)

    if not corroborating_sources:
        # If no API key, accept mock data but flag it
        if not SERPAPI_KEY:
            print(f"[Critic] ACCEPTED (mock mode): {title}")
            return _build_verified(topic, [], verified_by="mock-mode")
        print(f"[Critic] DISCARDED (no corroboration): {title}")
        return None

    # Need at least 1 independent source (different domain) to verify
    original_domain = _extract_domain(original_url)
    independent = [
        s for s in corroborating_sources if _extract_domain(s.get("link", "")) != original_domain
    ]

    if not independent:
        print(f"[Critic] DISCARDED (no independent source): {title}")
        return None

    print(f"[Critic] VERIFIED ({len(independent)} independent sources): {title}")
    return _build_verified(topic, independent, verified_by="cross-reference")


def _cross_search(title: str, retries: int) -> list[dict]:
    """Search for the title to find corroborating sources."""
    if not SERPAPI_KEY:
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "q": title,
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "num": 5,
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("organic_results", [])
        except (requests.RequestException, ValueError) as exc:
            print(f"[Critic] Attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    return []


def _extract_domain(url: str) -> str:
    """Extract domain from URL for independence check."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return url


def _build_verified(
    topic: dict, independent_sources: list[dict], verified_by: str
) -> dict:
    """Build a verified topic entry with citations."""
    return {
        "title": topic.get("title", ""),
        "url": topic.get("url", ""),
        "snippet": topic.get("snippet", ""),
        "source": topic.get("source", ""),
        "date": topic.get("date", ""),
        "domain": topic.get("domain", ""),
        "verification": {
            "status": "verified",
            "method": verified_by,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "independent_sources": [
                {
                    "title": s.get("title", ""),
                    "url": s.get("link", ""),
                    "source": s.get("source", ""),
                }
                for s in independent_sources[:3]
            ],
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> str:
    """Execute the Critic pipeline. Returns output file path."""
    print(f"[Critic] Starting verification at {datetime.now(timezone.utc).isoformat()}")

    # Load Scout output
    if not os.path.exists(SCOUT_INPUT):
        print(f"[Critic] ERROR: Scout output not found at {SCOUT_INPUT}")
        print("[Critic] Run scout.py first.")
        sys.exit(1)

    with open(SCOUT_INPUT, "r", encoding="utf-8") as f:
        scout_data = json.load(f)

    topics = scout_data.get("topics", [])
    print(f"[Critic] Loaded {len(topics)} topics from Scout")

    # Verify each topic
    verified: list[dict] = []
    discarded = 0

    for topic in topics:
        result = verify_against_source(topic)
        if result:
            verified.append(result)
        else:
            discarded += 1

    # Write verified_data.json
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scout_source": SCOUT_INPUT,
        "summary": {
            "total_input": len(topics),
            "verified": len(verified),
            "discarded": discarded,
        },
        "verified_topics": verified,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[Critic] Results: {len(verified)} verified, {discarded} discarded")
    print(f"[Critic] Saved to {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    run()
