
"""
Enhanced page scraper with Schema.org Product extraction.
"""
import requests
import json
import re
from bs4 import BeautifulSoup
from typing import Dict, Optional

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def extract_page_info(url: str) -> Dict:
    """Extract comprehensive page info including Schema.org Product data."""
    info = {
        "url": url,
        "title": "",
        "description": "",
        "image": None,
        "price": None,
        "currency": "USD",
        "availability": "",
        "sku": "",
        "brand": "",
        "schema_product": None,
    }

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        # Open Graph / Twitter Card
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            info["title"] = og_title["content"][:300].strip()
        elif soup.title:
            info["title"] = soup.title.get_text()[:300].strip()

        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            info["description"] = og_desc["content"][:1000]
        else:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                info["description"] = meta_desc["content"][:1000]

        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            info["image"] = og_img["content"]
        else:
            twitter_img = soup.find("meta", attrs={"name": "twitter:image"})
            if twitter_img and twitter_img.get("content"):
                info["image"] = twitter_img["content"]

        # -------- Schema.org Product Extraction --------
        schema = _extract_schema_product(soup)
        if schema:
            info["schema_product"] = schema
            info["price"] = schema.get("price") or info["price"]
            info["currency"] = schema.get("currency", "USD")
            info["availability"] = schema.get("availability", "")
            info["sku"] = schema.get("sku", "")
            info["brand"] = schema.get("brand", "")

        # Fallback price extraction
        if not info["price"]:
            for attrs in (
                {"property": "product:price:amount"},
                {"itemprop": "price"},
                {"class": re.compile(r"price", re.I)},
            ):
                tag = soup.find("meta", attrs=attrs) if "property" in attrs or "itemprop" in attrs else soup.find(attrs=attrs)
                if tag:
                    val = tag.get("content") or tag.get_text(" ", strip=True)
                    if val:
                        info["price"] = val[:50]
                        break

    except Exception as e:
        info["description"] = f"(Could not load page: {e})"

    return info


def _extract_schema_product(soup: BeautifulSoup) -> Optional[Dict]:
    """Extract Product schema from JSON-LD or Microdata."""
    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") == "Product":
                        return _parse_schema_product(item)
            elif data.get("@type") == "Product":
                return _parse_schema_product(data)
        except Exception:
            continue

    # Microdata
    product_scope = soup.find(itemtype=re.compile(r"Product"))
    if product_scope:
        return _parse_microdata_product(product_scope)

    return None


def _parse_schema_product(data: Dict) -> Dict:
    """Parse JSON-LD Product object."""
    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    brand = data.get("brand", {})
    if isinstance(brand, dict):
        brand = brand.get("name", "")

    return {
        "name": data.get("name", ""),
        "price": str(offers.get("price", "")),
        "currency": offers.get("priceCurrency", "USD"),
        "availability": offers.get("availability", "").split("/")[-1] if offers.get("availability") else "",
        "sku": data.get("sku", ""),
        "brand": brand,
        "image": data.get("image", ""),
        "description": data.get("description", ""),
    }


def _parse_microdata_product(scope) -> Dict:
    """Parse Microdata Product."""
    def get_prop(itemprop):
        el = scope.find(itemprop=itemprop)
        return el.get("content") or el.get_text(" ", strip=True) if el else ""

    return {
        "name": get_prop("name"),
        "price": get_prop("price"),
        "currency": get_prop("priceCurrency") or "USD",
        "availability": get_prop("availability").split("/")[-1] if get_prop("availability") else "",
        "sku": get_prop("sku"),
        "brand": get_prop("brand"),
        "image": get_prop("image"),
        "description": get_prop("description"),
    }