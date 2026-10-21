"""LIVE data sources — work for ANY brand/product/website:
1. Wikidata API          -> official website of virtually any known brand (free, no key)
2. Google Safe Browsing  -> Google's real-time phishing/malware database
3. Live page fetching    -> real content of any webpage
4. Community reports     -> web search for scam discussions about a domain
Everything cached in live_cache.json (1-7 days) for speed + free-quota safety.
"""
import json
import os
import time
import requests
from urllib.parse import urlparse

from config import SAFE_BROWSING_API_KEY
from search import ddg_text_search

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GenuineShopAI/1.0)"}
CACHE_FILE = "live_cache.json"


# ---------------- cache ----------------
def _load():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


_CACHE = _load()


def cache_get(key, ttl=7 * 24 * 3600):
    hit = _CACHE.get(key)
    if hit and time.time() - hit["ts"] < ttl:
        return hit["value"]
    return None


def cache_set(key, value):
    _CACHE[key] = {"ts": time.time(), "value": value}
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _domain_of(u):
    if not u:
        return ""
    if not u.startswith("http"):
        u = "https://" + u
    return urlparse(u).netloc.lower().replace("www.", "")


# -------- 1. Wikidata: official site of ANY brand --------
def official_site_wikidata(brand, limit_entities=3):
    """P856 = 'official website' on Wikidata. Covers nearly every known brand."""
    domains = []
    try:
        r = requests.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbsearchentities", "search": brand,
                    "language": "en", "format": "json", "limit": str(limit_entities)},
            headers=HEADERS, timeout=8)
        ids = [e["id"] for e in r.json().get("search", []) if e.get("id")]
    except Exception:
        return []
    for qid in ids:
        try:
            r2 = requests.get(
                "https://www.wikidata.org/w/api.php",
                params={"action": "wbgetclaims", "entity": qid,
                        "property": "P856", "format": "json"},
                headers=HEADERS, timeout=8)
            for c in r2.json().get("claims", {}).get("P856", []):
                d = _domain_of(c.get("mainsnak", {}).get("datavalue", {}).get("value"))
                if d and d not in domains:
                    domains.append(d)
        except Exception:
            continue
    return domains


# -------- 2. Google Safe Browsing (real-time phishing DB) --------
def safe_browsing(url):
    """True = flagged phishing/malware. False = clean. None = key not configured."""
    if not SAFE_BROWSING_API_KEY:
        return None
    key = f"sb::{_domain_of(url)}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    body = {
        "client": {"clientId": "genuineshop-ai", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING",
                            "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }
    try:
        r = requests.post(
            "https://safebrowsing.googleapis.com/v4/threatMatches:find",
            params={"key": SAFE_BROWSING_API_KEY}, json=body, timeout=8)
        flagged = bool(r.json().get("matches"))
        cache_set(key, flagged)
        return flagged
    except Exception:
        return None


# -------- 3. Live page fetching --------
def fetch_page_text(url, max_chars=4000):
    key = f"page::{url}"
    cached = cache_get(key, ttl=24 * 3600)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if "html" not in r.headers.get("content-type", ""):
            text = ""
        else:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ", strip=True).split())[:max_chars]
    except Exception:
        text = ""
    cache_set(key, text)
    return text


# -------- 4. Community scam reports --------
def community_scam_reports(domain):
    """Pages whose TITLE contains this domain AND scam/fraud words."""
    key = f"reports::{domain}"
    cached = cache_get(key, ttl=24 * 3600)
    if cached is not None:
        return cached
    hits = []
    try:
        for r in ddg_text_search(f'"{domain}" scam review', max_results=10):
            title = (r.get("title") or "").lower()
            clean = title.replace("scamadviser", "").replace("scam advisor", "")
            if domain in title and any(w in clean for w in
                    ("scam", "fraud", "fake", "complaint", "cheat", "legit")):
                hits.append(r.get("title") or "")
    except Exception:
        pass
    cache_set(key, hits)
    return hits