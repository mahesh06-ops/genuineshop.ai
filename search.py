from urllib.parse import urlparse

try:
    from ddgs import DDGS            # new package name
except ImportError:
    from duckduckgo_search import DDGS  # old package name (fallback)

def find_seller_urls(query, max_results=10):
    """Search the web for sites selling this product. One URL per domain."""
    try:
        results = DDGS().text(f"{query} buy online", max_results=max_results)
    except Exception:
        return []
    seen, urls = set(), []
    for r in results:
        u = r.get("href") or r.get("link") or r.get("url")
        if not u or not u.startswith("http"):
            continue
        d = urlparse(u).netloc.replace("www.", "")
        if d and d not in seen:
            seen.add(d)
            urls.append(u)
    return urls