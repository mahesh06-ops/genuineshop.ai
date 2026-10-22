"""
RAG Engine — Brand registry with vector search + fallback identification.
"""
import re
import json
from urllib.parse import urlparse
from typing import Dict, List, Optional, Any
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

# -------- Brand Registry (Extended) --------
REGISTRY = [
    {
        "brand": "Nike",
        "aliases": ["air force", "air max", "jordan", "dunk", "react", "pegasus", "zoom", "free", "metcon"],
        "official_domains": ["nike.com"],
        "official_site": "https://www.nike.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Myntra", "Foot Locker"],
        "known_scam_patterns": [
            "nike-shoes-sale", "nike-factory-outlet", "cheap-nike", "nike-outlet-store",
            "nike-discount", "nike-clearance", "nike-sale-online", "nike-store-sale"
        ],
        "notes": "Nike never sells via Instagram DM/WhatsApp. 80% off claims are scams.",
    },
    {
        "brand": "Apple",
        "aliases": ["iphone", "ipad", "macbook", "airpods", "imac", "apple watch", "vision pro", "mac mini", "mac studio"],
        "official_domains": ["apple.com"],
        "official_site": "https://www.apple.com",
        "authorized_retailers": ["Amazon", "Walmart", "Best Buy", "Flipkart", "Croma", "Reliance Digital"],
        "known_scam_patterns": [
            "iphone-sale-cheap", "apple-store-discount", "cheap-iphone", "iphone-liquidation",
            "apple-clearance", "macbook-sale-cheap"
        ],
        "notes": "Apple rarely discounts new iPhones. Unrealistic prices = scam. Check serial on checkcoverage.apple.com",
    },
    {
        "brand": "Samsung",
        "aliases": ["galaxy", "galaxy s", "galaxy z", "galaxy a", "galaxy buds", "galaxy watch", "galaxy tab"],
        "official_domains": ["samsung.com"],
        "official_site": "https://www.samsung.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Croma", "Best Buy", "Reliance Digital", "Vijay Sales"],
        "known_scam_patterns": [
            "samsung-mega-sale", "galaxy-deals-cheap", "samsung-factory-sale",
            "galaxy-s-cheap", "samsung-clearance"
        ],
        "notes": "Verify IMEI on Samsung's official site after purchase.",
    },
    {
        "brand": "Adidas",
        "aliases": ["ultraboost", "superstar", "samba", "yeezy", "gazelle", "stan smith", "nmd", "forum"],
        "official_domains": ["adidas.com", "adidas.co.in"],
        "official_site": "https://www.adidas.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Myntra", "Foot Locker"],
        "known_scam_patterns": [
            "adidas-outlet-sale", "cheap-adidas", "adidas-clearance",
            "adidas-factory-outlet", "yeezy-sale-cheap"
        ],
        "notes": "Check for 'adidas' authenticity tag inside the shoe tongue.",
    },
    {
        "brand": "Sony",
        "aliases": ["playstation", "ps5", "ps4", "wh1000", "bravia", "alpha", "xperia", "linkbuds"],
        "official_domains": ["sony.com", "playstation.com"],
        "official_site": "https://www.sony.com",
        "authorized_retailers": ["Amazon", "Walmart", "Best Buy", "Flipkart", "Croma", "Reliance Digital"],
        "known_scam_patterns": [
            "ps5-cheap-sale", "sony-deal-discount", "playstation5-offer",
            "wh1000xm5-cheap", "sony-clearance"
        ],
        "notes": "PS5 below MRP from unknown sites is almost always a scam.",
    },
    {
        "brand": "JBL",
        "aliases": ["flip 6", "charge 5", "tunebeam", "live pro", "tour one", "go 3", "clip 4"],
        "official_domains": ["jbl.com"],
        "official_site": "https://www.jbl.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Croma", "Best Buy", "Reliance Digital"],
        "known_scam_patterns": [
            "jbl-speaker-sale", "cheap-jbl", "jbl-factory-outlet",
            "jbl-headphones-cheap", "jbl-clearance"
        ],
        "notes": "Counterfeit JBL speakers are extremely common on ad-linked sites.",
    },
    {
        "brand": "boAt",
        "aliases": ["boat rockerz", "boat airdopes", "boat nirvana", "boat stone", "boat wave"],
        "official_domains": ["boat-lifestyle.com"],
        "official_site": "https://www.boat-lifestyle.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Myntra"],
        "known_scam_patterns": [
            "boat-sale-cheap", "boat-nirvana-offer", "boat-factory-sale",
            "airdopes-cheap", "boat-clearance"
        ],
        "notes": "Fake boAt sites often ask for UPI payment to personal IDs.",
    },
    {
        "brand": "OnePlus",
        "aliases": ["oneplus 12", "oneplus 11", "nord", "oneplus buds", "oneplus watch", "oneplus pad"],
        "official_domains": ["oneplus.com", "oneplus.in"],
        "official_site": "https://www.oneplus.com",
        "authorized_retailers": ["Amazon", "Best Buy", "Flipkart"],
        "known_scam_patterns": [
            "oneplus-sale-cheap", "oneplus-nord-offer", "oneplus-cheap",
            "oneplus-factory-outlet"
        ],
        "notes": "OnePlus primarily sells via its own site and Amazon.",
    },
    {
        "brand": "Dyson",
        "aliases": ["v15", "v12", "v11", "v10", "airwrap", "supersonic", "corrale", "zone"],
        "official_domains": ["dyson.com", "dyson.in"],
        "official_site": "https://www.dyson.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Croma", "Reliance Digital"],
        "known_scam_patterns": [
            "dyson-sale-cheap", "dyson-v15-offer", "dyson-airwrap-cheap",
            "dyson-clearance", "dyson-outlet"
        ],
        "notes": "Dyson never sells refurbished via third-party sites. Serial verification on dyson.com.",
    },
    {
        "brand": "Asics",
        "aliases": ["gel kayano", "gel nimbus", "gt-2000", "novablast", "metaspeed", "gel cumulus"],
        "official_domains": ["asics.com", "asics.co.in"],
        "official_site": "https://www.asics.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Foot Locker"],
        "known_scam_patterns": [
            "asics-sale-cheap", "asics-running-shoes-cheap", "asics-outlet",
            "gel-kayano-cheap"
        ],
        "notes": "Check for AHAR rubber outsole and GEL technology markings.",
    },
    {
        "brand": "Puma",
        "aliases": ["rs-x", "suede", "clyde", "future rider", "palermo", "speedcat"],
        "official_domains": ["puma.com", "puma.in"],
        "official_site": "https://www.puma.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Myntra", "Foot Locker"],
        "known_scam_patterns": [
            "puma-sale-cheap", "puma-shoes-discount", "puma-outlet-store",
            "puma-clearance-sale"
        ],
        "notes": "Puma India sold via puma.in and authorized retailers only.",
    },
    {
        "brand": "New Balance",
        "aliases": ["990", "550", "574", "993", "1080", "fresh foam", "fuelcell"],
        "official_domains": ["newbalance.com", "newbalance.in"],
        "official_site": "https://www.newbalance.com",
        "authorized_retailers": ["Amazon", "Flipkart", "Foot Locker"],
        "known_scam_patterns": [
            "new-balance-sale-cheap", "newbalance-outlet", "nb-shoes-cheap",
            "550-cheap", "990-cheap"
        ],
        "notes": "Made in USA/UK models have specific labels. Verify on newbalance.com.",
    },
]

# Backward-compatible name used by pipeline.py
BRANDS = REGISTRY

# Marketplace search links
RETAILERS = {
    "Amazon": {
        "domain": "amazon.in",
        "search_url": "https://www.amazon.in/s?k={q}"
    },
    "Flipkart": {
        "domain": "flipkart.com",
        "search_url": "https://www.flipkart.com/search?q={q}"
    },
    "Myntra": {
        "domain": "myntra.com",
        "search_url": "https://www.myntra.com/{qd}"
    },
    "Foot Locker": {
        "domain": "footlocker.com",
        "search_url": "https://www.footlocker.com/search?query={q}"
    },
    "Walmart": {
        "domain": "walmart.com",
        "search_url": "https://www.walmart.com/search?q={q}"
    },
    "Best Buy": {
        "domain": "bestbuy.com",
        "search_url": "https://www.bestbuy.com/site/searchpage.jsp?st={q}"
    },
    "Target": {
        "domain": "target.com",
        "search_url": "https://www.target.com/s?searchTerm={q}"
    },
    "Croma": {
        "domain": "croma.com",
        "search_url": "https://www.croma.com/searchB?q={q}"
    },
    "Reliance Digital": {
        "domain": "reliancedigital.in",
        "search_url": "https://www.reliancedigital.in/search?q={q}"
    },
    "Vijay Sales": {
        "domain": "vijaysales.com",
        "search_url": "https://www.vijaysales.com/search?q={q}"
    },
}


# -------- Vector Store (Optional Enhancement) --------
_VECTOR_STORE = None

def get_vector_store():
    global _VECTOR_STORE
    if _VECTOR_STORE is not None:
        return _VECTOR_STORE

    try:
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        _VECTOR_STORE = Chroma(
            persist_directory="./chroma_db",
            embedding_function=embeddings,
        )
    except Exception as e:
        print(f"Vector store init failed: {e}")
        _VECTOR_STORE = None
    return _VECTOR_STORE


def build_knowledge_base():
    """Build/update the vector store from brand registry."""
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    documents = []
    for entry in REGISTRY:
        text = (
            f"Brand: {entry['brand']}. "
            f"Official websites: {', '.join(entry['official_domains'])}. "
            f"Authorized retailers: {', '.join(entry['authorized_retailers'])}. "
            f"Known scam patterns: {', '.join(entry['known_scam_patterns'])}. "
            f"Safety notes: {entry['notes']}"
        )
        documents.append(Document(page_content=text, metadata={
            "brand": entry["brand"],
            "official_domains": entry["official_domains"],
            "authorized_retailers": entry["authorized_retailers"],
            "type": "brand_registry"
        }))

    Chroma.from_documents(documents, embeddings, persist_directory="./chroma_db")
    print(f"✅ Indexed {len(documents)} brands — using FREE local embeddings (no API key)")


def get_domain(url: str) -> str:
    """Return the normalized hostname for a URL."""
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().rstrip(".")
        return host.removeprefix("www.")
    except (ValueError, AttributeError):
        return ""


def find_brand_entry(product_info: Dict) -> Optional[Dict]:
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


def match_domain(url: str) -> Dict:
    """Conservative domain classification using known official domains."""
    domain = get_domain(url)

    if not domain:
        return {
            "status": "unknown",
            "reason": "Invalid or missing domain",
            "entry": None
        }

    # Check official domains
    for entry in REGISTRY:
        for official in entry.get("official_domains", []):
            if domain == official or domain.endswith("." + official):
                return {
                    "status": "official",
                    "reason": f"Matches official domain: {official}",
                    "entry": entry
                }

    # Check authorized retailer domains
    for retailer_name, retailer_info in RETAILERS.items():
        trusted = retailer_info["domain"]
        if domain == trusted or domain.endswith("." + trusted):
            return {
                "status": "authorized",
                "reason": f"Matches authorized retailer: {retailer_name} ({trusted})",
                "entry": None
            }

    # Check known scam patterns
    for entry in REGISTRY:
        for pattern in entry.get("known_scam_patterns", []):
            if pattern in domain:
                return {
                    "status": "scam_pattern",
                    "reason": f"Matches known scam pattern for {entry['brand']}: {pattern}",
                    "entry": entry
                }

    # Check typosquatting (brand-like domains)
    for entry in REGISTRY:
        brand_label = entry["brand"].lower().replace(" ", "")
        domain_label = domain.split(".")[0].lower()
        sim = SequenceMatcher(None, brand_label, domain_label).ratio()
        if 0.7 < sim < 1.0 and brand_label in domain_label:
            return {
                "status": "impersonation",
                "reason": f"Possible typosquatting of {entry['brand']} (similarity: {sim:.2f})",
                "entry": entry
            }

    return {
        "status": "unknown",
        "reason": "Domain not in verified registry",
        "entry": None
    }


def entry_retailer_names() -> List[str]:
    return list(RETAILERS.keys())


def identify_product_fallback(text: str) -> Dict:
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


# Import SequenceMatcher for match_domain
from difflib import SequenceMatcher