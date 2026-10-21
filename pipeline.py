from vision import identify_product_from_image, identify_product_from_text
from page_scraper import extract_page_info
from seller_finder import (build_genuine_links, get_avoid_list, search_web_sellers,
                           classify_sellers, get_product_image, guess_official_site)
from rag_engine import (match_domain, find_brand_entry, get_domain,
                        identify_product_fallback, BRANDS)
from verifier import WebsiteVerifier

verifier = WebsiteVerifier()

def _analyze_product(product_info):
    genuine = build_genuine_links(product_info)
    avoid = get_avoid_list(product_info)
    query = product_info.get("search_query") or product_info.get("product_name") or ""
    try:
        found = search_web_sellers(query)
    except Exception:
        found = []
    cls = classify_sellers(product_info, found)
    seen = {get_domain(l["url"]) for l in genuine}
    for g in cls["genuine"]:
        d = get_domain(g["url"])
        if d not in seen:
            seen.add(d)
            genuine.append({"seller": g["title"][:70] or d, "url": g["url"],
                            "status": "VERIFIED SELLER (live search)"})
    return {"product_info": product_info, "genuine_links": genuine,
            "avoid": avoid + cls["avoid"]}

# ---------- MODE 1: image ----------
def analyze_image(image_bytes):
    product_info = identify_product_from_image(image_bytes)
    if not product_info or not (product_info.get("brand") or product_info.get("product_name")):
        return {"error": "no_ai"}          # UI will show instructions
    return _analyze_product(product_info)

# ---------- MODE 2: product name ----------
def analyze_name(name):
    try:
        product_info = identify_product_from_text(name)
    except Exception:
        product_info = None
    if not product_info:
        product_info = identify_product_fallback(name)   # works with ZERO keys
    result = _analyze_product(product_info)
    result["image"] = get_product_image(product_info.get("search_query") or name)
    return result

# ---------- MODE 3: website link ----------
def analyze_url(url):
    if "://" not in url:
        url = "https://" + url
    page = extract_page_info(url)

    text = f"{page.get('title','')} {page.get('description','')}".strip()
    product_info = None
    if text:
        try:
            product_info = identify_product_from_text(text)
        except Exception:
            product_info = None
    if not product_info:
        product_info = identify_product_fallback(text or url)   # zero-key fallback
    product_info.setdefault("search_query", product_info.get("product_name", ""))

    m = match_domain(url)
    entry = find_brand_entry(product_info) or m.get("entry")
    official_domains = entry["official_domains"] if entry else \
                       [d for e in BRANDS for d in e["official_domains"]]

    verdict = verifier.decide(url, m, official_domains,
                              page_price=page.get("price"),
                              est_price_range=product_info.get("estimated_price_range"))

    genuine = build_genuine_links(product_info)

    if entry:
        real_site = {"seller": f"{entry['brand']} — Official Website",
                     "url": entry["official_site"]}
    else:
        real_site = None
        brand = (product_info.get("brand") or "").strip()
        if brand:
            real_site = guess_official_site(brand)

    return {"page": page, "product_info": product_info, "verdict": verdict,
            "genuine_links": genuine, "real_site": real_site}