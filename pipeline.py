from concurrent.futures import ThreadPoolExecutor
import knowledge_base as kb
import verifier
import search
import live_lookup as live
import gemini_client as gc


class Engine:

    def __init__(self):
        self.col = kb.build_or_load()   # local DB = optional speed booster now

    # ---------- LIVE brand profile (cached 7 days) ----------
    def brand_profile(self, brand):
        brand = (brand or "").strip()
        if not brand or brand.lower() in ("unknown", "n/a", "none"):
            return {"brand": "", "official": [], "confirmed": [],
                    "retailers": [], "price_note": ""}
        key = f"brand::{brand.lower()}"
        cached = live.cache_get(key)
        if cached:
            return cached

        wiki = [d for d in live.official_site_wikidata(brand) if d]   # source 1
        info = gc.brand_info_search(brand) or {}                      # source 2
        gem = [d.replace("www.", "").lower()
               for d in info.get("official_website", []) if d]

        official = list(dict.fromkeys(wiki + gem))
        confirmed = [d for d in official if d in wiki and d in gem]   # 2-source agreement

        profile = {
            "brand": brand,
            "official": official,
            "confirmed": confirmed,
            "retailers": [d.replace("www.", "").lower()
                          for d in info.get("authorized_retailers", []) if d],
            "price_note": info.get("typical_price_note", ""),
        }
        live.cache_set(key, profile)
        return profile

    # ---------- full LIVE check of ONE url ----------
    def check_url(self, url, profile, product_info=None, deep=True):
        domain, _ = verifier.get_domain(url)
        profile = profile or {}
        official = list(profile.get("official", []))
        retailers = list(profile.get("retailers", []))

        rag = kb.match_website(self.col, url)              # local booster
        if rag.get("status") == "official" and domain not in official:
            official.append(domain)
        if rag.get("status") == "retailer" and domain not in retailers:
            retailers.append(domain)

        ctx = {
            "brand": profile.get("brand", ""),
            "official": official,
            "official_confirmed": profile.get("confirmed", []),
            "retailers": retailers,
            "safe_browsing": live.safe_browsing(url),      # Google's live phishing DB
        }

        known = verifier.matches(domain, official) or verifier.matches(domain, retailers)

        if deep and not known:
            # scrape + LLM-analyze the ACTUAL page (cached 1 day)
            ck = f"pageai::{url}"
            page = live.cache_get(ck, ttl=24 * 3600)
            if page is None:
                text = live.fetch_page_text(url)
                page = gc.analyze_page_llm(url, text, product_info or {}) if text else {}
                live.cache_set(ck, page or {})
            if page:
                ctx["page"] = page
                # auto-detect the brand from the page itself (works for ANY site)
                if not ctx["brand"] and page.get("detected_brand") not in (None, "", "unknown"):
                    b = page["detected_brand"]
                    prof2 = self.brand_profile(b)
                    ctx["brand"] = b
                    ctx["official"] = list(dict.fromkeys(ctx["official"] + prof2["official"]))
                    ctx["official_confirmed"] = prof2["confirmed"]
                    ctx["retailers"] = list(dict.fromkeys(ctx["retailers"] + prof2["retailers"]))
                    known = (verifier.matches(domain, ctx["official"])
                             or verifier.matches(domain, ctx["retailers"]))
            if not known:
                ctx["reports"] = live.community_scam_reports(domain)

        return verifier.analyze_site(url, ctx), ctx

    # ---------- Tabs 1 & 2: any product ----------
    def analyze_product(self, product_name=None, image_bytes=None, mime_type="image/jpeg"):
        if image_bytes:
            info = gc.identify_product_from_image(image_bytes, mime_type)
        else:
            info = {"brand": "unknown", "product_name": product_name,
                    "search_query": product_name}

        profile = self.brand_profile(info.get("brand", ""))

        urls = search.find_seller_urls(info.get("search_query") or product_name)
        if not urls:
            return info, [], "⚠️ Live search returned no results. Try again or use the Check-a-Website tab.", profile

        with ThreadPoolExecutor(max_workers=5) as ex:
            pairs = list(ex.map(lambda u: self.check_url(u, profile, info), urls))
        results = [r for r, _ in pairs]
        results.sort(key=lambda s: s["score"], reverse=True)

        report = gc.generate_report(info, results, profile.get("price_note", ""))
        return info, results, report, profile

    # ---------- Tab 3: any URL ----------
    def analyze_url(self, url, brand_hint=None):
        profile = self.brand_profile(brand_hint) if brand_hint else {}
        return self.check_url(url, profile, None, deep=True)