"""
Tavily Search Agent: web search for real-world information.
Uses Tavily Python SDK with in-memory cache and graceful degradation.
"""

import hashlib
import logging
from collections import OrderedDict

from tavily import TavilyClient

from search_config import (
    SEARCH_ENABLED,
    TAVILY_API_KEY,
    TAVILY_MAX_RESULTS,
    TAVILY_SUMMARY_MAX_CHARS,
    TAVILY_TOPIC_MAX_RESULTS,
    TAVILY_PAGE_MAX_RESULTS,
    TAVILY_SEARCH_TIMEOUT,
    CACHE_MAX_ENTRIES,
)

logger = logging.getLogger("smartppt.tavily")

# -- In-memory LRU cache ---------------------------------------------
_cache: OrderedDict[str, dict] = OrderedDict()


def _cache_key(query: str, max_results: int) -> str:
    raw = f"{query.strip().lower()}:{max_results}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> dict | None:
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _cache_set(key: str, value: dict):
    _cache[key] = value
    _cache.move_to_end(key)
    if len(_cache) > CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


# -- Tavily client init ----------------------------------------------
_client: TavilyClient | None = None


def _get_client() -> TavilyClient | None:
    global _client
    if _client is not None:
        return _client
    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY 未配置，联网搜索不可用")
        return None
    try:
        _client = TavilyClient(api_key=TAVILY_API_KEY)
        return _client
    except Exception as e:
        logger.error("TavilyClient 初始化失败: %s", e)
        return None


# -- Public API -------------------------------------------------------


def web_search(query: str, max_results: int = None) -> dict:
    """Search the web and return structured results.

    Args:
        query: Search query string.
        max_results: Max number of results (default from config).

    Returns:
        {
            "success": bool,
            "query": str,
            "results": [{"title": str, "content": str, "url": str}, ...],
            "summary": str,  # concatenated summaries
            "error": str | None,
        }
    """
    if not SEARCH_ENABLED:
        return _empty_result(query, "联网搜索已关闭")

    if max_results is None:
        max_results = TAVILY_MAX_RESULTS

    # Check cache
    key = _cache_key(query, max_results)
    cached = _cache_get(key)
    if cached is not None:
        logger.debug("Cache hit: %s", query[:50])
        return cached

    client = _get_client()
    if client is None:
        return _empty_result(query, "TavilyClient 不可用")

    try:
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=False,
        )
        raw_results = response.get("results", [])
        results = []
        for r in raw_results[:max_results]:
            content = r.get("content", "")
            if len(content) > TAVILY_SUMMARY_MAX_CHARS:
                content = content[:TAVILY_SUMMARY_MAX_CHARS] + "..."
            results.append(
                {
                    "title": r.get("title", ""),
                    "content": content,
                    "url": r.get("url", ""),
                }
            )

        summary = "\n".join(
            f"[{i+1}] {r['title']}: {r['content']}" for i, r in enumerate(results)
        )

        output = {
            "success": True,
            "query": query,
            "results": results,
            "summary": summary,
            "error": None,
        }
        _cache_set(key, output)
        return output

    except Exception as e:
        logger.warning("Tavily search failed for '%s': %s", query[:50], e)
        return _empty_result(query, str(e))


def search_for_topic(topic: str) -> dict:
    """Search for topic-level context before outline generation."""
    return web_search(topic, max_results=TAVILY_TOPIC_MAX_RESULTS)


def search_for_slide(title: str, key_points: list[str] = None) -> dict:
    """Search for slide-specific content before content expansion."""
    query = title
    if key_points:
        query += " " + " ".join(key_points[:2])
    return web_search(query, max_results=TAVILY_PAGE_MAX_RESULTS)


def _empty_result(query: str, error: str) -> dict:
    return {
        "success": False,
        "query": query,
        "results": [],
        "summary": "",
        "error": error,
    }


def clear_cache():
    """Clear the in-memory search cache."""
    _cache.clear()
    logger.info("Search cache cleared")
