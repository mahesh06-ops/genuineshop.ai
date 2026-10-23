import json
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

BASE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = BASE_DIR / "data" / "brand_registry.json"
CHROMA_DIR = BASE_DIR / "chroma_db"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def build_knowledge_base():
    """Build the local Chroma database from the brand registry."""
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)

    documents = []

    for entry in data["documents"]:
        text = (
            f"Brand: {entry['brand']}. "
            f"Official websites: {', '.join(entry['official_domains'])}. "
            f"Authorized retailers: {', '.join(entry['authorized_retailers'])}. "
            f"Known scam patterns: {', '.join(entry['known_scam_patterns'])}. "
            f"Safety notes: {entry['notes']}"
        )

        documents.append(
            Document(
                page_content=text,
                metadata={
                    "brand": entry["brand"],
                    "official_domains": entry["official_domains"],
                    "authorized_retailers": entry["authorized_retailers"],
                    "type": "brand_registry",
                },
            )
        )

    collection = Chroma.from_documents(
        documents=documents,
        embedding=_get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )

    print(
        f"Indexed {len(documents)} brands using free local embeddings."
    )
    return collection


def build_or_load():
    """Load the existing Chroma database, or build it if missing/empty."""
    embeddings = _get_embeddings()

    if CHROMA_DIR.exists():
        try:
            collection = Chroma(
                persist_directory=str(CHROMA_DIR),
                embedding_function=embeddings,
            )
            if collection._collection.count() > 0:
                return collection
        except Exception as exc:
            print(f"Existing knowledge base could not be loaded: {exc}")

    return build_knowledge_base()


def match_website(collection, url):
    """Match a URL against the verified brand registry."""
    from urllib.parse import urlparse

    host = (urlparse(url if "://" in url else "//" + url).hostname or "").lower()
    host = host.removeprefix("www.").rstrip(".")

    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
    except Exception as exc:
        return {"status": "unknown", "reason": f"Brand registry unavailable: {exc}"}

    for entry in registry.get("documents", []):
        domains = entry.get("official_domains", [])
        retailers = entry.get("authorized_retailers", [])

        for domain in domains:
            d = str(domain).lower().strip().removeprefix("https://").removeprefix("http://")
            d = d.split("/")[0].removeprefix("www.").rstrip(".")
            if host == d or host.endswith("." + d):
                return {
                    "status": "official",
                    "reason": f"Domain matches the official website for {entry.get('brand', 'this brand')}",
                    "entry": entry,
                }

        for retailer in retailers:
            d = str(retailer).lower().strip().removeprefix("https://").removeprefix("http://")
            d = d.split("/")[0].removeprefix("www.").rstrip(".")
            if d and (host == d or host.endswith("." + d)):
                return {
                    "status": "authorized",
                    "reason": f"Domain matches a registered authorized retailer for {entry.get('brand', 'this brand')}",
                    "entry": entry,
                }

    # Use semantic retrieval as supporting context, but don't treat similarity
    # alone as proof that an unknown website is fraudulent or genuine.
    try:
        collection.similarity_search(f"Website URL: {url}", k=3)
    except Exception:
        pass

    return {
        "status": "unknown",
        "reason": "Domain not found in the verified brand registry",
    }

