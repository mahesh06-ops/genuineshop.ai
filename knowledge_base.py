import json
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

def build_knowledge_base():
    with open("data/brand_registry.json") as f:
        data = json.load(f)

    # FREE embeddings — runs on your machine, no API key.
    # First run downloads a ~90MB model, then works offline forever.
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    documents = []
    for entry in data["documents"]:
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
            "type": "brand_registry"}))

    Chroma.from_documents(documents, embeddings, persist_directory="./chroma_db")
    print(f"✅ Indexed {len(documents)} brands — using FREE local embeddings (no API key)")

if __name__ == "__main__":
    build_knowledge_base()