"""
Enhanced search module with multiple free backends.
"""
import os
import hashlib
from urllib.parse import urlparse, quote_plus
from typing import List, Dict
from config import get_keys, features_enabled, CACHE_FILE
import json
import time

# Cache helpers
def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

_CACHE = _load_cache()

def _save_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

def cache_get(key, ttl=7*24*3600):
    hit = _CACHE.get(key)
    if hit and time.time() - hit["ts"] < ttl:
        return hit["value"]
    return None

def cache_set(key, value):
    _CACHE[key] = {"ts": time.time(), "value": value}
    _save_cache()


# -------- DuckDuckGo (Primary - Free, No Key) --------
def ddg_text_search(query: str, max_results: int = 10) -> List[Dict]:
    """Raw live web search via DuckDuckGo. Free, no API key."""
    key = f"ddg::{hashlib.md5(query.encode()).hexdigest()[:16]}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        # Normalize
        normalized = []
        for r in results:
            normalized.append({
                "title": r.get("title", ""),
                "href": r.get("href", "") or r.get("link", "") or r.get("url", ""),
                "snippet": r.get("body", "") or r.get("snippet", ""),
            })
        cache_set(key, normalized)
        return normalized
    except Exception as e:
        print(f"DDG search error: {e}")
    return []


def ddg_images_search(query: str, max_results: int = 5) -> List[str]:
    """Free product image search."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=max_results))
        urls = []
        for r in results:
            u = r.get("thumbnail") or r.get("image")
            if u:
                urls.append(u)
        return urls
    except Exception:
        return []


# -------- Seller URL Discovery --------
def find_seller_urls(query: str, max_results: int = 10) -> List[str]:
    """Find unique domains selling the product."""
    seen, urls = set(), []
    search_query = f"buy {query} online"
    for r in ddg_text_search(search_query, max_results=max_results):
        u = r.get("href") or r.get("link") or r.get("url")
        if not u or not u.startswith("http"):
            continue
        d = urlparse(u).netloc.replace("www.", "")
        if d and d not in seen:
            seen.add(d)
            urls.append(u)
    return urls


# -------- Site-Restricted Search (Google CSE) --------
def search_site_restricted(query: str, site: str, max_results: int = 5) -> List[Dict]:
    """Search a specific site using Google Custom Search."""
    keys = get_keys()
    if not keys.has_google_cse():
        return []

    key = f"cse::{site}::{hashlib.md5(query.encode()).hexdigest()[:16]}"
    cached = cache_get(key, ttl=24*3600)
    if cached is not None:
        return cached

    try:
        q = f"site:{site} {query}"
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": keys.google_cse_key,
                "cx": keys.google_cse_cx,
                "q": q,
                "num": min(max_results, 10),
            },
            timeout=15,
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            results = []
            for item in items:
                link = item.get("link", "")
                if link.startswith("http"):
                    results.append({
                        "title": item.get("title", "")[:100],
                        "url": link,
                        "domain": site,
                        "snippet": item.get("snippet", "")[:200],
                    })
            cache_set(key, results)
            return results
    except Exception as e:
        print(f"CSE site search error: {e}")
    return []


# -------- SerpAPI Fallback --------
def serpapi_search(query: str, max_results: int = 10) -> List[Dict]:
    keys = get_keys()
    if not keys.serpapi:
        return []

    key = f"serp::{hashlib.md5(query.encode()).hexdigest()[:16]}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        from serpapi import GoogleSearch
        raw = GoogleSearch({
            "q": query,
            "api_key": keys.serpapi,
            "num": max_results,
        }).get_dict()

        results = []
        for r in raw.get("organic_results", [])[:max_results]:
            link = r.get("link", "")
            if link.startswith("http"):
                results.append({
                    "title": r.get("title", ""),
                    "url": link,
                    "domain": urlparse(link).netloc.replace("www.", ""),
                    "snippet": r.get("snippet", ""),
                })
        cache_set(key, results)
        return results
    except Exception as e:
        print(f"SerpAPI error: {e}")
    return []


# Import requests at module level for search_site_restricted
import requests