from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS


def ddg_text_search(query, max_results=10):
    """Raw live web search. Free, no API key."""
    try:
        return list(DDGS().text(query, max_results=max_results))
    except Exception:
        return []


def find_seller_urls(query, max_results=10):
    seen, urls = set(), []
    for r in ddg_text_search(f"{query} buy online", max_results=max_results):
        u = r.get("href") or r.get("link") or r.get("url")
        if not u or not u.startswith("http"):
            continue
        d = urlparse(u).netloc.replace("www.", "")
        if d and d not in seen:
            seen.add(d)
            urls.append(u)
    return urls