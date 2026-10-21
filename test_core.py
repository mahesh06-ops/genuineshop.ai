from knowledge_base import build_or_load, match_website
from verifier import analyze_site
from search import find_seller_urls

col = build_or_load()
print(f"✅ Knowledge base loaded: {col.count()} brands indexed\n")

print("URL verification tests:")
for url in ["https://www.amazon.com", "https://www.nike.com", "https://nike-shoes-sale.xyz"]:
    rag = match_website(col, url)
    res = analyze_site(url, rag)
    print(f"  {url:35} → {res['category']:11} {res['score']:3}/100")

print("\nWeb search test:")
urls = find_seller_urls("Nike Air Force 1 buy online")
for u in urls[:5]:
    print("  ", u)