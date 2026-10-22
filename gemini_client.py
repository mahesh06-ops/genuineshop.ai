"""
Gemini Client — Enhanced with Google Search Grounding for real-time data.
"""
import json
import re
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types
from config import get_keys

MODEL = "gemini-1.5-flash"  # Free tier model with grounding support


def _get_client() -> Optional[genai.Client]:
    keys = get_keys()
    if not keys.has_gemini():
        return None
    return genai.Client(api_key=keys.gemini)


def _extract_json(text: str) -> Optional[Dict]:
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


def _search_tool_config() -> types.GenerateContentConfig:
    """Google Search grounding tool config."""
    try:
        return types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    except Exception:
        return types.GenerateContentConfig(tools=[{"google_search": {}}])


def identify_product_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> Dict:
    """Analyze product image with Gemini (grounded if needed)."""
    client = _get_client()
    if not client:
        return _fallback_image_result()

    prompt = """Analyze this product image (likely from an online ad).
Return ONLY valid JSON:
{
  "brand": "brand name or 'unknown'",
  "product_name": "specific product name/model",
  "category": "product category",
  "search_query": "optimal search query to find this exact product",
  "estimated_price_range": "rough price range in USD (e.g., $90 - $120)",
  "key_features": ["feature1", "feature2"],
  "colors": ["color1"],
  "model_numbers": ["model1"]
}"""
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=[
                prompt,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        result = _extract_json(resp.text) or _fallback_image_result()
        # Validate required fields
        result.setdefault("brand", "unknown")
        result.setdefault("product_name", "unknown")
        result.setdefault("search_query", result.get("product_name", "product"))
        return result
    except Exception as e:
        print(f"Gemini image analysis error: {e}")
        return _fallback_image_result()


def _fallback_image_result() -> Dict:
    return {
        "brand": "unknown",
        "product_name": "unknown",
        "category": "",
        "search_query": "product",
        "estimated_price_range": "",
        "key_features": [],
        "colors": [],
        "model_numbers": [],
    }


def identify_product_from_text(text: str) -> Dict:
    """Extract product details from text using Gemini."""
    client = _get_client()
    if not client:
        return _fallback_text_result()

    prompt = f"""Website/product text:
"{text[:2000]}"

What product is being sold? Return ONLY valid JSON:
{{
  "brand": "brand name or empty string",
  "product_name": "specific product name/model",
  "category": "product category",
  "search_query": "optimal search query: brand + model",
  "estimated_price_range": "rough price range in USD (e.g., $90 - $120)",
  "key_features": ["feature1", "feature2"],
  "colors": ["color1"],
  "model_numbers": ["model1"]
}}"""
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        result = _extract_json(resp.text) or _fallback_text_result()
        result.setdefault("brand", "")
        result.setdefault("product_name", "")
        result.setdefault("search_query", text[:100])
        return result
    except Exception as e:
        print(f"Gemini text analysis error: {e}")
        return _fallback_text_result()


def _fallback_text_result() -> Dict:
    return {
        "brand": "",
        "product_name": "",
        "category": "",
        "search_query": "",
        "estimated_price_range": "",
        "key_features": [],
        "colors": [],
        "model_numbers": [],
    }


def brand_info_search(brand: str) -> Dict:
    """LIVE: Gemini searches Google for official brand info."""
    client = _get_client()
    if not client:
        return {}

    prompt = f"""Search the web for the brand "{brand}" and answer:
1. official_website: the brand's official shopping website domain(s) ONLY, e.g. ["asics.com"]
2. authorized_retailers: well-known authorized online retailers that genuinely sell this brand (global + India), as domains
3. typical_price_note: one line about the normal price range of this brand's products
Return ONLY JSON:
{{
  "official_website": ["..."],
  "authorized_retailers": ["..."],
  "typical_price_note": "..."
}}"""
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=_search_tool_config(),
        )
        return _extract_json(resp.text) or {}
    except Exception as e:
        print(f"Brand info search error: {e}")
        return {}


def analyze_page_llm(url: str, page_text: str, product_info: Dict = None) -> Dict:
    """LIVE: Judge ACTUAL content of a webpage for scam indicators."""
    client = _get_client()
    if not client:
        return {"verdict": "unknown", "reason": "LLM not available"}

    product_info = product_info or {}
    prompt = f"""You are an online scam analyst. Analyze this shopping webpage.

URL: {url}
Product context: {product_info.get('product_name', '')} (brand: {product_info.get('brand', 'unknown')})
Expected price range: {product_info.get('estimated_price_range', 'unknown')}

PAGE TEXT (may be truncated):
\"\"\"{page_text[:5000]}\"\"\"

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
  "reason": "one short sentence explaining the verdict",
  "confidence": 0-100
}}"""
    try:
        resp = client.models.generate_content(model=MODEL, contents=prompt)
        result = _extract_json(resp.text)
        if result:
            result.setdefault("verdict", "unknown")
            result.setdefault("confidence", 50)
        return result or {"verdict": "unknown", "reason": "Analysis failed"}
    except Exception as e:
        print(f"Page LLM analysis error: {e}")
        return {"verdict": "unknown", "reason": f"Analysis error: {e}"}


def generate_report(product_info: Dict, sites: List[Dict], price_note: str = "") -> str:
    """Generate human-readable safety report."""
    client = _get_client()
    if not client:
        return "Report generation requires Gemini API key."

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