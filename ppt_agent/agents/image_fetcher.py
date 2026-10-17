"""
Image Fetcher Agent: visual search keywords -> image bytes + metadata from Unsplash.
Tries multiple keywords (specific -> broad) until one returns results.
Thread-safe cache for concurrent access.
"""
import logging
import threading
import requests
from io import BytesIO
from collections import OrderedDict
from config import UNSPLASH_KEY

logger = logging.getLogger("smartppt.image_fetcher")

UNSPLASH_BASE = "https://api.unsplash.com"
HEADERS = {"Authorization": f"Client-ID {UNSPLASH_KEY}"} if UNSPLASH_KEY else {}

MAX_CACHE = 50
_cache: OrderedDict[str, dict | None] = OrderedDict()
_cache_lock = threading.Lock()


def fetch_image(keyword, topic="") -> dict | None:
    """Search Unsplash, return a dict with bytes + author metadata, or None.

    Args:
        keyword: A single keyword string or a list of keywords (specific -> broad).
        topic: The main PPT topic (English), used as a last-resort fallback.

    Returns:
        {"bytes": BytesIO, "alt_description": str, "description": str,
         "url": str, "width": int|None, "height": int|None} or None
    """
    if not UNSPLASH_KEY:
        logger.warning("UNSPLASH_ACCESS_KEY not configured, skipping image fetch")
        return None

    if isinstance(keyword, str):
        keywords = [keyword]
    else:
        keywords = list(keyword)

    if topic:
        topic_list = [topic] if isinstance(topic, str) else list(topic)
        for tk in topic_list:
            if tk and tk not in keywords:
                keywords.append(tk)

    cache_key = keywords[0] if keywords else ""
    with _cache_lock:
        if cache_key in _cache:
            cached = _cache[cache_key]
            _cache.move_to_end(cache_key)
            if cached is not None:
                cached["bytes"].seek(0)
            return cached

    for query in keywords:
        if not query:
            continue
        meta = _search_unsplash(query)
        if meta is not None:
            with _cache_lock:
                _cache[cache_key] = meta
                _evict_cache()
            return meta

    with _cache_lock:
        _cache[cache_key] = None
        _evict_cache()
    return None


def fetch_image_bytes(keyword, topic="") -> BytesIO | None:
    """Backward-compatible wrapper returning only the image bytes."""
    meta = fetch_image(keyword, topic)
    return meta["bytes"] if meta else None


def _evict_cache():
    """Evict oldest entries when cache exceeds MAX_CACHE. Caller must hold _cache_lock."""
    while len(_cache) > MAX_CACHE:
        _cache.popitem(last=False)


def _search_unsplash(query: str) -> dict | None:
    """Search Unsplash for a single query, return image dict or None."""
    try:
        resp = requests.get(
            f"{UNSPLASH_BASE}/search/photos",
            headers=HEADERS,
            params={
                "query": query,
                "orientation": "landscape",
                "per_page": 5,
                "order_by": "relevant",
            },
            timeout=10,
        )
        if resp.status_code == 403:
            logger.warning("Unsplash API rate limit or forbidden for '%s'", query)
            return None
        if resp.status_code == 401:
            logger.error("Unsplash API unauthorized — check UNSPLASH_ACCESS_KEY")
            return None
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            logger.info("No results for '%s'", query)
            return None

        result = results[0]
        image_url = result["urls"]["regular"]
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()
        meta = {
            "bytes": BytesIO(img_resp.content),
            "alt_description": (result.get("alt_description") or "").strip(),
            "description": (result.get("description") or "").strip(),
            "url": image_url,
            "width": result.get("width"),
            "height": result.get("height"),
        }
        logger.info("Image found: '%s' (%d bytes)", query, len(img_resp.content))
        return meta

    except requests.exceptions.Timeout:
        logger.warning("Timeout fetching image for '%s'", query)
    except requests.exceptions.RequestException as e:
        logger.warning("Request failed for '%s': %s", query, e)
    except (KeyError, IndexError) as e:
        logger.warning("Unexpected Unsplash response for '%s': %s", query, e)
    except Exception as e:
        logger.warning("Error '%s': %s", query, e)
    return None
