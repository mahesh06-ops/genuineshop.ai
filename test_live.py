from live_lookup import official_site_wikidata, fetch_page_text, safe_browsing
import gemini_client as gc

print("1) Wikidata LIVE lookup (brands NOT in brands.json):")
for brand in ["Asics", "Puma", "New Balance", "Dyson"]:
    print(f"   {brand:12} -> {official_site_wikidata(brand)}")

print("\n2) LIVE page fetch:")
t = fetch_page_text("https://www.asics.com")
print(f"   got {len(t)} chars:", t[:80], "...")

print("\n3) Gemini + LIVE Google Search grounding:")
print("  ", gc.brand_info_search("Asics"))

print("\n4) Google Safe Browsing (None = key not set):")
print("   test URL ->", safe_browsing("https://testsafebrowsing.appspot.com/s/malware.html"))