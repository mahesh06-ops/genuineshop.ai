import json
import re
from google import genai
from google.genai import types
from config import GEMINI_API_KEY

MODEL = "gemini-4argon"
client = genai.Client(api_key=GEMINI_API_KEY)


def _extract_json(text):
    """Robustly pull JSON from an LLM reply (handles ```json fences)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _search_tool_config():
    """Google Search grounding, with fallback for SDK version differences."""
    try:
        return types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())])
    except Exception:
        return types.GenerateContentConfig(tools=[{"google_search": {}}])


def identify_product_from_image(image_bytes, mime_type="image/jpeg"):
    prompt = """Analyze this product image (likely from an online ad).
Return ONLY valid JSON:
{"brand": "brand name or 'unknown'", "product_name": "specific product name",
 "category": "product category", "search_query": "good search query to find sellers",
 "typical_price_range": "rough price range"}"""
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return _extract_json(resp.text) or {
            "brand": "unknown", "product_name": "unknown", "category": "",
            "search_query": "product", "typical_price_range": ""}
    except Exception as e:
        print("identify error:", e)
        return {"brand": "unknown", "product_name": "unknown", "category": "",
                "search_query": "product", "typical_price_range": ""}


def brand_info_search(brand):
    """LIVE: Gemini searches Google right now and answers with real results."""
    prompt = f"""Search the web for the brand "{brand}" and answer:
1. official_website: the brand's official shopping website domain(s) ONLY, e.g. ["asics.com"]
2. authorized_retailers: well-known authorized online retailers that genuinely sell this
   brand (global + India), as domains
3. typical_price_note: one line about the normal price range of this brand's products
Return ONLY JSON:
{{"official_website": ["..."], "authorized_retailers": ["..."], "typical_price_note": "..."}}"""
    try:
        resp = client.models.generate_content(
            model=MODEL, contents=prompt, config=_search_tool_config())
        return _extract_json(resp.text) or {}
    except Exception as e:
        print("brand_info_search error:", e)
        return {}


def analyze_page_llm(url, page_text, product_info=None):
    """LIVE: judge the ACTUAL content of a webpage for scam indicators."""
    product_info = product_info or {}
    prompt = f"""You are an online scam analyst. Analyze this shopping webpage.

URL: {url}
Product context: {product_info.get('product_name', '')} (brand: {product_info.get('brand', 'unknown')})

PAGE TEXT (may be truncated):
\"\"\"{page_text}\"\"\"

Return ONLY JSON:
{{
 "detected_brand": "main brand being sold, or 'unknown'",
 "detected_product": "product name if visible",
 "detected_price": "price string if visible, else ''",
 "price_too_low": false,
 "missing_business_info": false,
 "poor_quality_indicators": false,
 "payment_red_flags": false,
 "verdict": "legitimate" | "suspicious" | "scam",
 "reason": "one short sentence"
}}"""
    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        return _extract_json(resp.text)
    except Exception as e:
        print("analyze_page_llm error:", e)
        return None


def generate_report(product_info, sites, price_note=""):
    lines = []
    for s in sites:
        p = f" | price found: {s['price']}" if s.get("price") else ""
        lines.append(f"- {s['domain']} | {s['score']}/100 {s['category']}{p} | "
                     + "; ".join(s["signals"]))
    prompt = f"""You are an online-shopping safety expert helping real people avoid scam websites.

Product: {product_info.get('product_name', 'N/A')} (brand: {product_info.get('brand', 'unknown')})
Typical market price for this brand: {price_note or 'not known'}

Live analysis of websites selling it:
{chr(10).join(lines)}

Write a report with these sections:
1. **✅ Safe to buy from** — ranked, with reasons
2. **🚨 Avoid** — with reasons
3. **⚠️ Price sanity check** — compare found prices vs typical; call out too-good-to-be-true offers
4. **💡 Best recommendation** — the single best domain + one safety tip
Under 250 words, simple language, use the actual domains."""
    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        return resp.text
    except Exception as e:
        return f"⚠️ Report generation failed: {e}"