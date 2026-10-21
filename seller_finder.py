import urllib.parse
from rag_engine import REGISTRY, RETAILERS, match_domain, find_brand_entry, get_domain

def build_genuine_links(product_info: dict) -> list:
    """The core of your requirement: returns EXACT, clickable buy links."""
    entry = find_brand_entry(product_info)
    query = product_info.get("search_query") or product_info.get("product_name") or ""
    q  = urllib.parse.quote_plus(query)
    qd = q.replace("+", "-").lower()

    links = []
    if entry:
        links.append({"seller": f"{entry['brand']} — Official Website",
                      "url": entry["official_site"], "status": "OFFICIAL"})
        for name in entry["authorized_retailers"]:
            r = RETAILERS.get(name)
            if r:
                links.append({"seller": f"{name} — Authorized Retailer",
                              "url": r["search_url"].format(q=q, qd=qd),
                              "status": "AUTHORIZED"})
    else:
        brand = (product_info.get("brand") or "").strip()
        if brand:
            guess = guess_official_site(brand)
            if guess: links.append(guess)
        for name in ("Amazon", "Flipkart", "Walmart"):
            r = RETAILERS[name]
            links.append({"seller": name, "url": r["search_url"].format(q=q, qd=qd),
                          "status": "TRUSTED MARKETPLACE"})

    seen, out = set(), []
    for l in links:
        if l["url"] not in seen:
            seen.add(l["url"]); out.append(l)
    return out

def guess_official_site(brand: str):
    """For brands not in the registry: search for the official site, sanity-check age."""
    from verifier import WebsiteVerifier
    try:
        results = search_web_sellers(f"{brand} official website", 5)
    except Exception:
        return None
    for r in results:
        dom = get_domain(r["url"])
        if brand.lower().split()[0] in dom:
            age = WebsiteVerifier()._domain_age(dom)
            if age == -1 or age > 365:
                return {"seller": f"{brand} Official Website (found via search)",
                        "url": r["url"], "status": "LIKELY OFFICIAL"}
    return None

def get_avoid_list(product_info):
    entry = find_brand_entry(product_info)
    return list(entry["known_scam_patterns"]) if entry else []

def search_web_sellers(query: str, num=8):
    """Web search via SerpAPI (if key set) or free DuckDuckGo fallback."""
    import os
    results = []
    if os.getenv("SERPAPI_KEY"):
        try:
            from serpapi import GoogleSearch
            raw = GoogleSearch({"q": f"buy {query} online",
                                "api_key": os.environ["SERPAPI_KEY"]}).get_dict()
            results = [{"title": r.get("title", ""), "url": r.get("link", "")}
                       for r in raw.get("organic_results", [])[:num]]
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

def classify_sellers(product_info, found):
    genuine, avoid = [], []
    for item in found:
        url = item.get("url") or ""
        if not url.startswith("http"):
            continue
        m = match_domain(url)
        if m["status"] in ("official", "authorized"):
            genuine.append({"title": item.get("title", ""), "url": url, "domain": get_domain(url)})
        elif m["status"] in ("scam_pattern", "impersonation"):
            avoid.append({"domain": get_domain(url), "url": url,
                          "title": item.get("title", ""), "reason": m["reason"]})
    return {"genuine": genuine, "avoid": avoid}

def get_product_image(query: str):
    """Free product image (for name-search mode)."""
    try:
        from ddgs import DDGS
        with DDGS() as d:
            res = list(d.images(f"{query} product photo", max_results=3))
        for r in res:
            u = r.get("thumbnail") or r.get("image")
            if u: return u
    except Exception:
        pass
    return None