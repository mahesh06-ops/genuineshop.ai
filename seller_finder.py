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


def build_genuine_links(product_info: Dict) -> List[Dict]:
    """
    Build EXACT, clickable buy links — prioritized:
    1. Official brand website (direct product page if found)
    2. Authorized retailers (direct product search)
    3. Trusted marketplaces (search results)
    """
    entry = find_brand_entry(product_info)
    query = product_info.get("search_query") or product_info.get("product_name") or ""
    brand = product_info.get("brand", "").strip()

    q = urllib.parse.quote_plus(query)
    qd = q.replace("+", "-").lower()

    links = []

    # -------- 1. OFFICIAL BRAND WEBSITE --------
    official_domains = []
    official_site_url = None

    if entry:
        official_domains = entry.get("official_domains", [])
        official_site_url = entry.get("official_site")
    else:
        # Dynamic lookup via Wikidata for unknown brands
        if brand:
            official_domains = official_site_wikidata(brand)
            if official_domains:
                official_site_url = f"https://{official_domains[0]}"

    # Try to find DIRECT product page on official site
    if official_domains and query:
        print(f"[DEBUG] Searching official domains for product: {official_domains}")
        official_products = search_official_site(brand or entry["brand"] if entry else brand, query, official_domains)
        for prod in official_products[:3]:  # Top 3 results
            avail = check_product_availability(prod["url"])
            links.append({
                "seller": f"{brand or (entry['brand'] if entry else 'Brand')} — Official Website",
                "url": prod["url"],
                "status": "OFFICIAL",
                "availability": avail,
                "domain": prod["domain"],
                "snippet": prod.get("snippet", ""),
            })

    # If no direct product found, add official homepage
    if official_site_url and not any(l["status"] == "OFFICIAL" for l in links):
        links.append({
            "seller": f"{brand or (entry['brand'] if entry else 'Brand')} — Official Website",
            "url": official_site_url,
            "status": "OFFICIAL",
            "availability": {"available": None, "confidence": 0, "reason": "Homepage - search for product"},
            "domain": official_domains[0] if official_domains else "",
        })

    # -------- 2. AUTHORIZED RETAILERS (Direct Product Search) --------
    authorized = entry["authorized_retailers"] if entry else []
    for name in authorized:
        retailer = RETAILERS.get(name)
        if not retailer:
            continue
        search_url = retailer["search_url"].format(q=q, qd=qd)
        # Try to get first product result via SerpAPI or DDG
        direct_url = _get_first_product_result(search_url, name, query)
        links.append({
            "seller": f"{name} — Authorized Retailer",
            "url": direct_url or search_url,
            "status": "AUTHORIZED",
            "availability": {"available": None, "confidence": 0, "reason": "Search results page"},
            "domain": retailer["domain"],
        })

    # -------- 3. TRUSTED MARKETPLACES (Fallback) --------
    for name in ("Amazon", "Flipkart", "Walmart", "Best Buy", "Target"):
        if name in authorized:
            continue
        retailer = RETAILERS.get(name)
        if not retailer:
            continue
        search_url = retailer["search_url"].format(q=q, qd=qd)
        direct_url = _get_first_product_result(search_url, name, query)
        links.append({
            "seller": name,
            "url": direct_url or search_url,
            "status": "TRUSTED MARKETPLACE",
            "availability": {"available": None, "confidence": 0, "reason": "Search results page"},
            "domain": retailer["domain"],
        })

    # Deduplicate
    seen, out = set(), []
    for l in links:
        if l["url"] not in seen:
            seen.add(l["url"])
            out.append(l)
    return out


def _get_first_product_result(search_url: str, retailer_name: str, query: str) -> Optional[str]:
    """Try to extract first actual product URL from a marketplace search page."""
    # Try SerpAPI first for structured results
    keys = get_keys()
    if keys.serpapi:
        try:
            from serpapi import GoogleSearch
            raw = GoogleSearch({
                "q": f"site:{search_url.split('/')[2]} {query}",
                "api_key": keys.serpapi,
                "num": 3,
            }).get_dict()
            for r in raw.get("organic_results", []):
                link = r.get("link", "")
                if link.startswith("http") and "/dp/" in link or "/product/" in link or "/p/" in link:
                    return link
        except Exception:
            pass

    # Fallback: return search URL (user will see results)
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
    """Web search via SerpAPI (if key set) or free DuckDuckGo fallback."""
    keys = get_keys()
    results = []

    if keys.serpapi:
        try:
            from serpapi import GoogleSearch
            raw = GoogleSearch({
                "q": f"buy {query} online",
                "api_key": keys.serpapi,
            }).get_dict()
            results = [{
                "title": r.get("title", ""),
                "url": r.get("link", "")
            } for r in raw.get("organic_results", [])[:num]]
        except Exception:
            pass

    if not results:
        try:
            from ddgs import DDGS
            with DDGS() as d:
                for r in d.text(f"buy {query} online", max_results=num):
                    results.append({"title": r.get("title", ""), "url": r.get("href", "")})
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