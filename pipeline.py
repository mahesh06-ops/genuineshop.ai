from concurrent.futures import ThreadPoolExecutor
import knowledge_base as kb
import verifier
import search
import gemini_client as gc

class Engine:
    def __init__(self):
        self.col = kb.build_or_load()

    def analyze_url(self, url):
        """Check a single URL (for the 'Check a Website' tab)."""
        rag = kb.match_website(self.col, url)
        return verifier.analyze_site(url, rag), rag

    def analyze_product(self, product_name=None, image_bytes=None, mime_type="image/jpeg"):
        """Full pipeline: identify product → find sellers → verify each → report."""
        # Step 1: identify product
        if image_bytes:
            info = gc.identify_product_from_image(image_bytes, mime_type)
        else:
            info = {"brand": "unknown", "product_name": product_name,
                    "search_query": product_name}

        # Step 2: find selling websites
        urls = search.find_seller_urls(info.get("search_query") or product_name)
        if not urls:
            return info, [], "⚠️ Web search returned no results. Please try again, or use the **Check a Website** tab to verify a specific URL."

        # Steps 3+4: verify each website in parallel (WHOIS/SSL are slow)
        def work(u):
            rag = kb.match_website(self.col, u)
            return verifier.analyze_site(u, rag)

        with ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(work, urls))

        # Step 5: rank + LLM report
        results.sort(key=lambda s: s["score"], reverse=True)
        report = gc.generate_report(info, results)
        return info, results, report