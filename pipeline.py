"""
Main Pipeline â€” Orchestrates all analysis modes with real-time data.
"""
from vision import identify_product_from_image, identify_product_from_text
from page_scraper import extract_page_info
from seller_finder import (
    build_genuine_links,
    get_avoid_list,
    search_web_sellers,
    classify_sellers,
    get_product_image,
    guess_official_site,
)
from rag_engine import match_domain, find_brand_entry, get_domain, BRANDS, identify_product_fallback
from verifier import WebsiteVerifier
from live_lookup import official_site_wikidata, check_product_availability
from config import get_keys

verifier = WebsiteVerifier()


def _analyze_product(product_info: Dict) -> Dict:
    """Core product analysis: genuine links + avoid list + live search classification."""
    genuine = build_genuine_links(product_info)
    avoid = get_avoid_list(product_info)

    query = product_info.get("search_query") or product_info.get("product_name") or ""
    try:
        found = search_web_sellers(query)
    except Exception as e:
        print(f"Web search error: {e}")
        found = []

    cls = classify_sellers(product_info, found)

    # Merge live search results into genuine links
    seen = {get_domain(l["url"]) for l in genuine}
    for g in cls["genuine"]:
        d = get_domain(g["url"])
        if d not in seen:
            seen.add(d)
            genuine.append({
                "seller": g["title"][:70] or d,
                "url": g["url"],
                "status": "VERIFIED SELLER (live search)",
                "availability": {"available": None, "confidence": 0, "reason": "Live search result"},
                "domain": d,
            })

    return {
        "product_info": product_info,
        "genuine_links": genuine,
        "avoid": avoid + cls["avoid"]
    }


# ---------- MODE 1: Image Upload ----------
def analyze_image(image_bytes: bytes) -> Dict:
    """Analyze uploaded product image."""
    product_info = identify_product_from_image(image_bytes)
    if not product_info or not (product_info.get("brand") or product_info.get("product_name")):
        return {"error": "no_ai"}  # UI will show instructions
    return _analyze_product(product_info)


# ---------- MODE 2: Product Name ----------
def analyze_name(name: str) -> Dict:
    """Analyze product by name/text."""
    try:
        product_info = identify_product_from_text(name)
    except Exception as e:
        print(f"Text analysis error: {e}")
        product_info = None

    if not product_info:
        product_info = identify_product_fallback(name)  # Zero-key fallback

    result = _analyze_product(product_info)
    result["image"] = get_product_image(product_info.get("search_query") or name)
    return result


# ---------- MODE 3: Website Link Check ----------
def analyze_url(url: str) -> Dict:
    """Comprehensive website verification with real-time checks."""
    if "://" not in url:
        url = "https://" + url

    # Fetch page info
    page = extract_page_info(url)

    # Extract product info from page content
    text = f"{page.get('title', '')} {page.get('description', '')}".strip()
    product_info = None
    if text:
        try:
            product_info = identify_product_from_text(text)
        except Exception:
            product_info = None

    if not product_info:
        product_info = identify_product_fallback(text or url)
    product_info.setdefault("search_query", product_info.get("product_name", ""))

    # RAG domain match
    m = match_domain(url)
    entry = find_brand_entry(product_info) or m.get("entry")

    # Build official domains list
    official_domains = []
    if entry:
        official_domains = entry.get("official_domains", [])
    else:
        # Aggregate all known official domains
        for e in BRANDS:
            official_domains.extend(e.get("official_domains", []))
        # Add Wikidata lookup for detected brand
        brand = (product_info.get("brand") or "").strip()
        if brand:
            official_domains.extend(official_site_wikidata(brand))

    # Deduplicate
    official_domains = list(dict.fromkeys(official_domains))

    # Verifier decision
    verdict = verifier.decide(
        url, m, official_domains,
        page_price=page.get("price"),
        est_price_range=product_info.get("estimated_price_range")
    )

    # Build genuine links for this product
    genuine = build_genuine_links(product_info)

    # Determine real official site
    real_site = None
    if entry:
        real_site = {
            "seller": f"{entry['brand']} â€” Official Website",
            "url": entry["official_site"],
            "status": "OFFICIAL",
        }
    else:
        brand = (product_info.get("brand") or "").strip()
        if brand:
            real_site = guess_official_site(brand)

    # Check availability on real site if found
    if real_site and real_site.get("url"):
        avail = check_product_availability(real_site["url"])
        real_site["availability"] = avail

    return {
        "page": page,
        "product_info": product_info,
        "verdict": verdict,
        "genuine_links": genuine,
        "real_site": real_site,
    }

