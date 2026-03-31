import os
import sys
import json
import textwrap
from datetime import datetime, timedelta, timezone

import requests

API_URL = "https://newsapi.org/v2/everything"

# Keywords tuned for podiatry / foot health
QUERY = (
    "podiatry OR \"foot health\" OR \"plantar fasciitis\" "
    "OR bunions OR orthotics OR \"ankle injury\" OR \"running injury\""
)

# Prefer recent news (last 10 days)
DAYS_BACK = 10
MAX_RESULTS = 12
OUTPUT_FILE = "news-data.json"


def get_api_key() -> str:
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        print("ERROR: NEWSAPI_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return key


def build_params(api_key: str) -> dict:
    today = datetime.now(timezone.utc)
    from_date = (today - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")

    return {
        "apiKey": api_key,
        "q": QUERY,
        "language": "en",
        # Bias towards AU by preferring AU sources in the query text
        "sortBy": "publishedAt",
        "from": from_date,
        "pageSize": MAX_RESULTS,
    }


def summarise_description(text: str, *, max_chars: int = 280) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # Try to cut on sentence boundary
    cut = text.rfind(".", 0, max_chars)
    if cut == -1:
        cut = max_chars
    summary = text[:cut].rstrip()
    if not summary.endswith("."):
        summary += "…"
    return summary


def is_relevant(article: dict) -> bool:
    """Light filter to keep podiatry / lower-limb relevant items.

    We check title + description for a few key terms and try to avoid
    generic business/finance pieces.
    """
    title = (article.get("title") or "").lower()
    desc = (article.get("description") or "").lower()
    text = f"{title} {desc}"

    if not text.strip():
        return False

    keywords = [
        "podiatry",
        "podiatrist",
        "foot",
        "ankle",
        "plantar",
        "heel",
        "orthotic",
        "orthotics",
        "running",
        "gait",
        "diabetic foot",
    ]
    if not any(k in text for k in keywords):
        return False

    # Roughly filter out finance/stock market noise
    bad_words = ["stock", "shares", "earnings", "ipo", "price target"]
    if any(b in text for b in bad_words):
        return False

    return True


def transform_article(a: dict) -> dict:
    published_at = a.get("publishedAt") or ""
    try:
        # Normalise to ISO 8601 string if parsable
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        published_at = dt.astimezone(timezone.utc).isoformat()
    except Exception:
        # Keep original if parsing fails
        pass

    summary = summarise_description(a.get("description") or a.get("content") or "")

    # If description is empty, fall back to a short title-based line
    if not summary:
        summary = textwrap.shorten(a.get("title") or "Foot health update", width=180, placeholder="…")

    source_name = ""
    source = a.get("source") or {}
    if isinstance(source, dict):
        source_name = source.get("name") or "News source"
    else:
        source_name = str(source) or "News source"

    return {
        "title": a.get("title") or "Foot health article",
        "summary": summary,
        "url": a.get("url") or "",
        "source": source_name,
        "publishedAt": published_at,
    }


def fetch_news() -> dict:
    api_key = get_api_key()
    params = build_params(api_key)

    print("Fetching podiatry-related news from NewsAPI…", file=sys.stderr)
    resp = requests.get(API_URL, params=params, timeout=15)
    try:
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR: NewsAPI request failed: {e}", file=sys.stderr)
        print(resp.text[:500], file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    raw_articles = data.get("articles") or []

    filtered = [a for a in raw_articles if is_relevant(a)]
    transformed = [transform_article(a) for a in filtered]

    # Sort newest → oldest
    transformed.sort(key=lambda a: a.get("publishedAt") or "", reverse=True)

    # Limit to something reasonable for the UI
    transformed = transformed[:8]

    return {"articles": transformed}


def main() -> None:
    news = fetch_news()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(news.get('articles', []))} articles to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
