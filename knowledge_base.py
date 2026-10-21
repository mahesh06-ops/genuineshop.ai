import json
import chromadb

DB_PATH = "./chroma_db"

def build_or_load():
    """Create (or load) the vector database from brands.json."""
    db = chromadb.PersistentClient(path=DB_PATH)
    col = db.get_or_create_collection("brands", metadata={"hnsw:space": "cosine"})

    if col.count() == 0:
        with open("data/brands.json", encoding="utf-8") as f:
            brands = json.load(f)
        for i, b in enumerate(brands):
            text = (
                f"Brand: {b['brand']}. "
                f"Official websites: {', '.join(b['official_domains'])}. "
                f"Authorized retailers: {', '.join(b['authorized_retailers'])}. "
                f"Known scam patterns: {', '.join(b['known_scam_patterns'])}. "
                f"Notes: {b['notes']}"
            )
            col.add(
                ids=[str(i)],
                documents=[text],
                metadatas={
                    "brand": b["brand"],
                    "official_domains": ",".join(b["official_domains"]),
                    "authorized_retailers": ",".join(b["authorized_retailers"]),
                    "scam_patterns": ",".join(b["known_scam_patterns"]),
                },
            )
    return col

def match_website(col, url):
    """RAG retrieval: match a URL against the brand knowledge base."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower().replace("www.", "")
    if not domain:
        return {"status": "unknown", "brand": "", "official": [], "retailers": []}

    res = col.query(query_texts=[f"seller website domain {domain}"], n_results=3)

    for meta in res["metadatas"][0]:
        official = meta["official_domains"].split(",")
        retailers = meta["authorized_retailers"].split(",")
        scams = meta["scam_patterns"].split(",")

        if domain in official:
            return {"status": "official", "brand": meta["brand"],
                    "official": official, "retailers": retailers}
        if domain in retailers:
            return {"status": "retailer", "brand": meta["brand"],
                    "official": official, "retailers": retailers}
        if any(p and p in domain for p in scams):
            return {"status": "scam", "brand": meta["brand"],
                    "official": official, "retailers": retailers}

    # No exact match — return the closest brand (used for impersonation checks)
    best = res["metadatas"][0][0]
    return {"status": "unknown", "brand": best["brand"],
            "official": best["official_domains"].split(","),
            "retailers": best["authorized_retailers"].split(",")}