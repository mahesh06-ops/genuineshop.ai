"""
Seller Finder — The core module for finding EXACT, clickable official product links.
"""
import urllib.parse
import hashlib
from typing import List, Dict, Optional
from config import get_keys, features_enabled, TRUSTED_MARKETPLACES
from rag_engine import REGISTRY, RETAILERS, find_brand_entry, get_domain
from live_lookup import (
    official_site_wikidata,
    search_official_site,
    serpapi_search,
    check_product_availability,
)
from search import find_seller_urls, ddg_text_search


def _is_exact_product_link(url: str, query: str) -> bool:
    """Return True only for product-specific URLs, not homepages or generic search pages."""
    if not url or not url.startswith("http"):
        return False

    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "").lower()
    if not path or path in ("/", "/index.html"):
        return False

    # Filter obvious search/homepage/category results.
    blocked_tokens = (
        "/search", "/browse", "/shop", "/products", "/collections", "/category",
        "?q=", "&q=", "&search=", "?search=", "/?", "/all-products",
        "/cart", "/checkout", "/login", "/account"
    )
    if any(token in path.lower() for token in blocked_tokens):
        return False

    if any(token in parsed.netloc.lower() for token in ("google.", "bing.", "duckduckgo.", "search")):
        return False

    query_tokens = set((query or "").lower().replace("-", " ").split())
    text = f"{parsed.path} {parsed.query} {parsed.fragment}".lower()
    if not query_tokens:
        return "/" not in text or any(marker in text for marker in ("/dp/", "/product/", "/p/", "pid=", "sku="))

    has_product_marker = any(marker in text for marker in ("/dp/", "/product/", "/p/", "/item/", "sku=", "productid", "pid="))
    if has_product_marker:
        return True

    # Most exact listings include at least some product identifiers or a meaningful product term.
    return bool(query_tokens & set(text.replace("/", " ").split())) or bool(any(token in text for token in ["product", "sku", "model"]))


def build_genuine_links(product_info: Dict) -> List[Dict]:
    """Return only exact product URLs that are likely purchase pages, not generic search pages."""
    entry = find_brand_entry(product_info)
    query = product_info.get("search_query") or product_info.get("product_name") or ""
    brand = product_info.get("brand", "").strip()

    links = []

    # 1. Official brand website: only direct product pages, never a homepage fallback.
    official_domains = []
    if entry:
        official_domains = entry.get("official_domains", [])
    elif brand:
        official_domains = official_site_wikidata(brand)

    if official_domains and query:
        official_brand = brand or (entry["brand"] if entry else "Brand")
        official_products = search_official_site(official_brand, query, official_domains)
        for prod in official_products[:3]:
            url = prod.get("url", "")
            if not _is_exact_product_link(url, query):
                continue
            avail = check_product_availability(url)
            links.append({
                "seller": f"{official_brand} — Official Website",
                "url": url,
                "status": "OFFICIAL",
                "availability": avail,
                "domain": prod.get("domain", get_domain(url)),
                "snippet": prod.get("snippet", ""),
            })

    # 2. Authorized retailer pages: only exact product listings, not broad retailer search URLs.
    authorized = entry["authorized_retailers"] if entry else []
    for name in authorized:
        retailer = RETAILERS.get(name)
        if not retailer:
            continue
        direct_url = _get_first_product_result(retailer["search_url"], name, query)
        if not direct_url or not _is_exact_product_link(direct_url, query):
            continue
        links.append({
            "seller": f"{name} — Authorized Retailer",
            "url": direct_url,
            "status": "AUTHORIZED",
            "availability": {"available": None, "confidence": 0, "reason": "Exact listing identified"},
            "domain": retailer["domain"],
        })

    seen, out = set(), []
    for link in links:
        url = link.get("url")
        if url and url not in seen:
            seen.add(url)
            out.append(link)
    return out


def _get_first_product_result(search_url: str, retailer_name: str, query: str) -> Optional[str]:
    """Try to extract an exact product result from a retailer search page; otherwise return None."""
    keys = get_keys()
    if keys.serpapi:
        try:
            from serpapi import GoogleSearch
            domain = urllib.parse.urlparse(search_url).netloc.replace("www.", "")
            raw = GoogleSearch({
                "q": f"site:{domain} {query}",
                "api_key": keys.serpapi,
                "num": 5,
            }).get_dict()
            for r in raw.get("organic_results", []):
                link = r.get("link", "")
                if not link.startswith("http"):
                    continue
                if "/dp/" in link or "/product/" in link or "/p/" in link or "sku=" in link.lower() or "pid=" in link.lower():
                    return link
        except Exception:
            pass
    return None


def guess_official_site(brand: str) -> Optional[Dict]:
    """For brands not in registry: search for official site, sanity-check age."""
    from verifier import WebsiteVerifier
    try:
        results = find_seller_urls(f"{brand} official website", 5)
    except Exception:
        return None

    for r in results:
        dom = get_domain(r)
        if brand.lower().split()[0] in dom:
            age = WebsiteVerifier()._domain_age(dom)
            if age == -1 or age > 365:
                return {
                    "seller": f"{brand} Official Website (found via search)",
                    "url": r,
                    "status": "LIKELY OFFICIAL",
                    "availability": {"available": None, "confidence": 0, "reason": "Not verified"},
                    "domain": dom,
                }
    return None


def get_avoid_list(product_info: Dict) -> List[str]:
    entry = find_brand_entry(product_info)
    return list(entry.get("known_scam_patterns", [])) if entry else []


def search_web_sellers(query: str, num: int = 8) -> List[Dict]:
    """Search for likely product pages, never generic marketplace homepages or search results."""
    keys = get_keys()
    results = []

    if keys.serpapi:
        try:
            from serpapi import GoogleSearch
            raw = GoogleSearch({
                "q": f"{query} product buy",
                "api_key": keys.serpapi,
            }).get_dict()
            for r in raw.get("organic_results", [])[:num]:
                url = r.get("link", "")
                if url.startswith("http") and _is_exact_product_link(url, query):
                    results.append({"title": r.get("title", ""), "url": url})
        except Exception:
            pass

    if not results:
        try:
            from ddgs import DDGS
            with DDGS() as d:
                for r in d.text(f"{query} product", max_results=num):
                    url = r.get("href", "")
                    if url.startswith("http") and _is_exact_product_link(url, query):
                        results.append({"title": r.get("title", ""), "url": url})
        except Exception:
            pass

    return results


def classify_sellers(product_info: Dict, found: List[Dict]) -> Dict:
    """Classify found sellers as genuine/avoid based on domain matching."""
    from rag_engine import match_domain
    genuine, avoid = [], []

    for item in found:
        url = item.get("url") or ""
        if not url.startswith("http"):
            continue
        m = match_domain(url)
        if m["status"] in ("official", "authorized"):
            genuine.append({"title": item.get("title", ""), "url": url, "domain": get_domain(url)})
        elif m["status"] in ("scam_pattern", "impersonation"):
            avoid.append({
                "domain": get_domain(url),
                "url": url,
                "title": item.get("title", ""),
                "reason": m["reason"]
            })

    return {"genuine": genuine, "avoid": avoid}


def get_product_image(query: str) -> Optional[str]:
    """Free product image via DuckDuckGo."""
    from search import ddg_images_search
    return ddg_images_search(f"{query} product photo", max_results=3)[0] if ddg_images_search(f"{query} product photo") else None