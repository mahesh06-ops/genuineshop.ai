"""
LIVE data sources — work for ANY brand/product/website:
1. Wikidata API          -> official website of virtually any known brand (free, no key)
2. Google Safe Browsing  -> Google's real-time phishing/malware database (free key)
3. VirusTotal            -> Multi-engine domain reputation (free key)
4. URLVoid               -> 40+ engine domain scan (free key)
5. Google Custom Search  -> Site-restricted official product search (free key)
6. Live page fetching    -> real content of any webpage
7. Community reports     -> web search for scam discussions about a domain
Everything cached in live_cache.json (1-7 days) for speed + free-quota safety.
"""
import json
import os
import time
import hashlib
import requests
from urllib.parse import urlparse, quote_plus
from typing import Optional, List, Dict, Any

from config import get_keys, features_enabled, CACHE_TTL_DAYS, PAGE_CACHE_TTL_HOURS, MAX_PAGE_CHARS, REQUEST_TIMEOUT, SUSPICIOUS_TLDS
from search import ddg_text_search

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
CACHE_FILE = "live_cache.json"
# Cache domain reputation results for 24 hours
REPUTATION_CACHE_TTL_HOURS = 24

# ---------------- Cache ----------------
def _load_cache() -> dict:
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


def cache_get(key: str, ttl: int = CACHE_TTL_DAYS * 24 * 3600) -> Any:
    hit = _CACHE.get(key)
    if hit and time.time() - hit["ts"] < ttl:
        return hit["value"]
    return None


def cache_set(key: str, value: Any):
    _CACHE[key] = {"ts": time.time(), "value": value}
    _save_cache()


def _domain_of(url: str) -> str:
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return urlparse(url).netloc.lower().replace("www.", "")


def _cache_key(*parts: str) -> str:
    return "::".join(parts)


# -------- 1. Wikidata: Official Site of ANY Brand --------
def official_site_wikidata(brand: str, limit_entities: int = 3) -> List[str]:
    """P856 = 'official website' on Wikidata. Covers nearly every known brand."""
    key = _cache_key("wikidata", brand.lower())
    cached = cache_get(key)
    if cached is not None:
        return cached

    domains = []
    try:
        # Search for brand entities
        r = requests.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": brand,
                "language": "en",
                "format": "json",
                "limit": str(limit_entities),
            },
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        ids = [e["id"] for e in r.json().get("search", []) if e.get("id")]

        for qid in ids:
            r2 = requests.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbgetclaims",
                    "entity": qid,
                    "property": "P856",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            for c in r2.json().get("claims", {}).get("P856", []):
                val = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                d = _domain_of(val)
                if d and d not in domains:
                    domains.append(d)
    except Exception as e:
        print(f"Wikidata error for {brand}: {e}")

    cache_set(key, domains)
    return domains


# -------- 2. Google Safe Browsing --------
def safe_browsing_check(url: str) -> Optional[bool]:
    """True = flagged phishing/malware. False = clean. None = key not configured/error."""
    keys = get_keys()
    if not keys.has_safe_browsing():
        return None

    domain = _domain_of(url)
    key = _cache_key("sb", domain)
    cached = cache_get(key)
    if cached is not None:
        return cached

    body = {
        "client": {"clientId": "genuineshop-ai", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": [
                "MALWARE", "SOCIAL_ENGINEERING",
                "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"
            ],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }
    try:
        r = requests.post(
            "https://safebrowsing.googleapis.com/v4/threatMatches:find",
            params={"key": keys.safe_browsing},
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
        flagged = bool(r.json().get("matches"))
        cache_set(key, flagged)
        return flagged
    except Exception as e:
        print(f"Safe Browsing error: {e}")
        return None


# -------- 3. VirusTotal Domain Reputation --------
def virustotal_reputation(domain: str) -> Optional[Dict]:
    """Returns dict with 'malicious', 'suspicious', 'harmless' counts. None if no key/error."""
    keys = get_keys()
    if not keys.has_virustotal():
        return None

    key = _cache_key("vt", domain)
    cached = cache_get(key, ttl=REPUTATION_CACHE_TTL_HOURS * 3600)
    if cached is not None:
        return cached

    try:
        r = requests.get(
            f"https://www.virustotal.com/api/v3/domains/{domain}",
            headers={"x-apikey": keys.virustotal},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            result = {
                "malicious": stats.get("malicious", 0),
                "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0),
                "undetected": stats.get("undetected", 0),
            }
            cache_set(key, result)
            return result
    except Exception as e:
        print(f"VirusTotal error: {e}")
    return None


# -------- 4. URLVoid Scan --------
def urlvoid_scan(domain: str) -> Optional[Dict]:
    """Returns dict with 'detected' count and engine details. None if no key/error."""
    keys = get_keys()
    if not keys.has_urlvoid():
        return None

    key = _cache_key("uv", domain)
    cached = cache_get(key, ttl=REPUTATION_CACHE_TTL_HOURS * 3600)
    if cached is not None:
        return cached

    try:
        r = requests.get(
            "https://api.urlvoid.com/v1/scan",
            params={"key": keys.urlvoid, "host": domain},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            # Parse URLVoid response (structure varies)
            result = {"raw": data}
            cache_set(key, result)
            return result
    except Exception as e:
        print(f"URLVoid error: {e}")
    return None


# -------- 5. Google Custom Search: Official Product Search --------
def search_official_site(brand: str, product_query: str, official_domains: List[str]) -> List[Dict]:
    """
    Search ONLY the official brand domains for the product.
    Returns list of {title, url, domain} for direct product pages.
    """
    keys = get_keys()
    if not keys.has_google_cse():
        return []

    results = []
    for domain in official_domains[:3]:  # Limit to top 3 official domains
        key = _cache_key("cse", domain, hashlib.md5(product_query.encode()).hexdigest()[:16])
        cached = cache_get(key, ttl=PAGE_CACHE_TTL_HOURS * 3600)
        if cached is not None:
            results.extend(cached)
            continue

        try:
            # Site-restricted search
            q = f"site:{domain} {product_query}"
            r = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": keys.google_cse_key,
                    "cx": keys.google_cse_cx,
                    "q": q,
                    "num": 5,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                domain_results = []
                for item in items:
                    link = item.get("link", "")
                    if link.startswith("http"):
                        domain_results.append({
                            "title": item.get("title", "")[:100],
                            "url": link,
                            "domain": domain,
                            "snippet": item.get("snippet", "")[:200],
                        })
                cache_set(key, domain_results)
                results.extend(domain_results)
        except Exception as e:
            print(f"CSE error for {domain}: {e}")

    return results


# -------- 6. SerpAPI Fallback (Structured Results) --------
def serpapi_search(query: str, num: int = 10) -> List[Dict]:
    """Fallback structured search via SerpAPI."""
    keys = get_keys()
    if not keys.serpapi:
        return []

    key = _cache_key("serp", hashlib.md5(query.encode()).hexdigest()[:16])
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        from serpapi import GoogleSearch
        raw = GoogleSearch({
            "q": query,
            "api_key": keys.serpapi,
            "num": num,
        }).get_dict()

        results = []
        for r in raw.get("organic_results", [])[:num]:
            link = r.get("link", "")
            if link.startswith("http"):
                results.append({
                    "title": r.get("title", ""),
                    "url": link,
                    "domain": _domain_of(link),
                    "snippet": r.get("snippet", ""),
                })
        cache_set(key, results)
        return results
    except Exception as e:
        print(f"SerpAPI error: {e}")
    return []


# -------- 7. Live Page Fetching --------
def fetch_page_text(url: str, max_chars: int = MAX_PAGE_CHARS) -> str:
    """Fetch and extract clean text from a webpage."""
    key = _cache_key("page", url)
    cached = cache_get(key, ttl=PAGE_CACHE_TTL_HOURS * 3600)
    if cached is not None:
        return cached

    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if "html" not in r.headers.get("content-type", ""):
            text = ""
        else:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ", strip=True).split())[:max_chars]
    except Exception as e:
        print(f"Page fetch error for {url}: {e}")
        text = ""

    cache_set(key, text)
    return text


# -------- 8. Community Scam Reports --------
def community_scam_reports(domain: str) -> List[str]:
    """Pages whose TITLE contains this domain AND scam/fraud words."""
    key = _cache_key("reports", domain)
    cached = cache_get(key, ttl=24 * 3600)
    if cached is not None:
        return cached

    hits = []
    try:
        for r in ddg_text_search(f'"{domain}" scam review', max_results=10):
            title = (r.get("title") or "").lower()
            clean = title.replace("scamadviser", "").replace("scam advisor", "")
            if domain in title and any(w in clean for w in
                    ("scam", "fraud", "fake", "complaint", "cheat", "legit", "warning")):
                hits.append(r.get("title") or "")
    except Exception as e:
        print(f"Community reports error: {e}")

    cache_set(key, hits)
    return hits


# -------- 9. Domain Intelligence (WHOIS, SSL, Age) --------
def domain_intelligence(domain: str) -> Dict:
    """Comprehensive domain analysis: age, SSL, registrar, etc."""
    key = _cache_key("intel", domain)
    cached = cache_get(key, ttl=7 * 24 * 3600)
    if cached is not None:
        return cached

    import ssl, socket, whois
    from datetime import datetime, date
    from difflib import SequenceMatcher

    result = {
        "domain": domain,
        "domain_age_days": -1,
        "ssl_valid": False,
        "ssl_issuer": "",
        "ssl_expires": "",
        "is_ip_address": False,
        "has_suspicious_tld": any(domain.endswith(t) for t in SUSPICIOUS_TLDS),
        "registrar": "",
        "country": "",
    }

    # Domain age & WHOIS
    try:
        w = whois.whois(domain)
        c = w.creation_date
        if isinstance(c, list):
            c = c[0]
        if c:
            if isinstance(c, datetime):
                if c.tzinfo:
                    c = c.replace(tzinfo=None)
            elif isinstance(c, date):
                c = datetime(c.year, c.month, c.day)
            result["domain_age_days"] = (datetime.now() - c).days
        result["registrar"] = str(w.registrar or "")[:100]
        result["country"] = str(w.country or "")[:50]
    except Exception:
        pass

    # SSL Certificate
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                result["ssl_valid"] = True
                # Issuer
                issuer = dict(x[0] for x in cert.get("issuer", []))
                result["ssl_issuer"] = issuer.get("organizationName", "")[:100]
                # Expiry
                not_after = cert.get("notAfter")
                if not_after:
                    result["ssl_expires"] = not_after
    except Exception:
        pass

    # IP address check
    parts = domain.split(".")
    result["is_ip_address"] = len(parts) == 4 and all(p.isdigit() for p in parts)

    cache_set(key, result)
    return result


# -------- 10. Product Availability Check on Official Site --------
def check_product_availability(product_url: str) -> Dict:
    """
    Fetch product page and check for:
    - Schema.org Product markup
    - Price presence
    - Add to cart / Buy button
    - Out of stock indicators
    """
    text = fetch_page_text(product_url, max_chars=8000)
    if not text:
        return {"available": False, "confidence": 0, "reason": "Could not fetch page"}

    # Check for structured data
    has_schema = '"@type":"Product"' in text or '"@type": "Product"' in text
    has_price = any(x in text.lower() for x in ['"price"', '"pricecurrency"', 'itemprop="price"'])
    has_buy_button = any(x in text.lower() for x in [
        "add to cart", "buy now", "add to bag", "purchase", "add to basket",
        "comprar", "kaufen", "acheter", "acquista"
    ])
    out_of_stock = any(x in text.lower() for x in [
        "out of stock", "sold out", "unavailable", "notify me",
        "coming soon", "pre-order", "preorder"
    ])

    confidence = 0
    if has_schema: confidence += 30
    if has_price: confidence += 30
    if has_buy_button: confidence += 25
    if out_of_stock: confidence -= 40

    available = confidence >= 40 and not out_of_stock

    return {
        "available": available,
        "confidence": max(0, min(100, confidence)),
        "has_schema": has_schema,
        "has_price": has_price,
        "has_buy_button": has_buy_button,
        "out_of_stock": out_of_stock,
        "reason": "Product page validated" if available else "Product may be unavailable or page not a product page",
    }