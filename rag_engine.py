
import re
from urllib.parse import urlparse

# Known brand registry.
# Add more verified brands and authorized retailers as needed.
REGISTRY = [
    {
        "brand": "Apple",
        
        "official_site": "https://www.apple.com/",
        "official_domains": ["apple.com"],
        "aliases": ["iphone", "ipad", "macbook", "airpods"],
        "authorized_retailers": ["Amazon", "Flipkart"],
        "known_scam_patterns": []
    },

    {
        "brand": "Samsung",
        "official_site": "https://www.samsung.com/",
        "official_domains": ["samsung.com"],
        "aliases": ["galaxy", "galaxy s", "galaxy a"],
       
        "authorized_retailers": ["Amazon", "Flipkart"],
        "known_scam_patterns": []
    },
    {
        "brand": "Google",
        "aliases": ["pixel", "pixel phone"],
        "official_site": "https://store.google.com/",
        "official_domains": ["goggle.com"],
        "authorized_retailers": ["Amazon", "Flipkart"],
        "known_scam_patterns": []
    },
]
# Backward-compatible name used by pipeline.py
BRANDS = REGISTRY
# Marketplace search links.
RETAILERS = {
    "Amazon": {
        "search_url": "https://www.amazon.in/s?k={q}"
    },
    "Flipkart": {
        "search_url": "https://www.flipkart.com/search?q={q}"
    },
    "Walmart": {
        "search_url": "https://www.walmart.com/search?q={q}"
    },
}


def get_domain(url: str) -> str:
    """Return the normalized hostname for a URL."""
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().rstrip(".")
        return host.removeprefix("www.")
    except (ValueError, AttributeError):
        return ""


def find_brand_entry(product_info: dict):
    """Find a known brand using product name, brand, or search query."""
    text = " ".join(
        str(product_info.get(key) or "")
        for key in ("brand", "product_name", "search_query")
    ).lower()

    for entry in REGISTRY:
        names = [entry["brand"], *entry.get("aliases", [])]
        for name in names:
            if re.search(
                r"(?<![a-z0-9])" + re.escape(name.lower()) +
                r"(?![a-z0-9])",
                text
            ):
                return entry

    return None


def match_domain(url: str) -> dict:
    """Conservative domain classification using known official domains."""
    domain = get_domain(url)

    if not domain:
        return {
            "status": "unknown",
            "reason": "Invalid or missing domain",
            "entry": None
        }

    official_domains = {
        "Apple": ["apple.com"],
        "Samsung": ["samsung.com"],
        "Google": ["google.com", "google.co.in"],
    }

    for entry in REGISTRY:
        for official in official_domains.get(entry["brand"], []):
            if domain == official or domain.endswith("." + official):
                return {
                    "status": "official",
                    "reason": "Matches a configured official domain",
                    "entry": entry
                }

    authorized_domains = {
        "Amazon": ["amazon.in", "amazon.com"],
        "Flipkart": ["flipkart.com"],
        "Walmart": ["walmart.com"],
    }

    for retailer in entry_retailer_names():
        for trusted_domain in authorized_domains.get(retailer, []):
            if domain == trusted_domain or domain.endswith("." + trusted_domain):
                return {
                    "status": "authorized",
                    "reason": "Matches a configured retailer domain",
                    "entry": None
                }

    return {
        "status": "unknown",
        "reason": "Domain has not been verified by this registry",
        "entry": None
    }


def entry_retailer_names():
    """Return configured retailer names."""
    return list(RETAILERS.keys())

def identify_product_fallback(text: str) -> dict:
    """Identify a product brand without requiring an API key."""
    q = (text or "").lower()

    for entry in REGISTRY:
        names = [entry["brand"], *entry.get("aliases", [])]

        for name in names:
            if name.lower() in q:
                return {
                    "brand": entry["brand"],
                    "product_name": text or "",
                    "search_query": text or "",
                    "estimated_price_range": "",
                }

    return {
        "brand": "",
        "product_name": text or "",
        "search_query": text or "",
        "estimated_price_range": "",
    }
