
"""
Gemini Client — Google Search grounding with Groq fallback.
Gemini remains the primary provider; Groq provides text-only fallback.
"""

import json
import re
from typing import Dict, Any, Optional, List

from google import genai
from google.genai import types
from config import get_keys

MODEL = "gemini-3.8-flash"


def _get_client() -> Optional[genai.Client]:
    keys = get_keys()
    if not keys.has_gemini():
        return None
    return genai.Client(api_key=keys.gemini)


def _extract_json(text: str) -> Optional[Dict]:
    """Extract a JSON object from an LLM response."""
    if not text:
        return None

    # Remove optional Markdown JSON fences.
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None

    try:
        result = json.loads(cleaned[start:end + 1])
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _search_tool_config() -> types.GenerateContentConfig:
    """Google Search grounding tool configuration."""
    try:
        return types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    except Exception:
        return types.GenerateContentConfig(tools=[{"google_search": {}}])


def _groq_text(prompt: str) -> Optional[str]:
    """Call the project's Groq client without making Groq mandatory."""
    try:
        from groq_client import analyze_text
        return analyze_text(prompt)
    except Exception as exc:
        print(f"Groq fallback error: {type(exc).__name__}: {exc}")
        return None


def _normalize_page_result(raw: Any) -> Optional[Dict]:
    """Normalize webpage-analysis results to the expected schema."""
    if isinstance(raw, dict):
        result = raw
    else:
        result = _extract_json(raw) if isinstance(raw, str) else None

    if not isinstance(result, dict):
        return None

    allowed_verdicts = {"legitimate", "suspicious", "scam", "unknown"}
    verdict = str(result.get("verdict", "unknown")).lower().strip()
    result["verdict"] = verdict if verdict in allowed_verdicts else "unknown"

    defaults = {
        "detected_brand": "unknown",
        "detected_product": "unknown",
        "detected_price": "",
        "price_too_low": False,
        "missing_business_info": False,
        "poor_quality_indicators": False,
        "payment_red_flags": False,
        "reason": "Insufficient evidence for a reliable conclusion.",
    }
    for key, value in defaults.items():
        result.setdefault(key, value)

    try:
        result["confidence"] = max(
            0, min(100, int(result.get("confidence", 0)))
        )
    except (ValueError, TypeError):
        result["confidence"] = 0

    return result


def identify_product_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Dict:
    """Identify a product from an image using Gemini."""
    client = _get_client()
    if not client:
        return _fallback_image_result()

    prompt = """Analyze this product image.
Return ONLY valid JSON with these keys:
{
  "brand": "brand name or unknown",
  "product_name": "specific product name/model",
  "category": "product category",
  "search_query": "brand plus exact model search query",
  "estimated_price_range": "rough price range in USD",
  "key_features": [],
  "colors": [],
  "model_numbers": []
}
Do not invent a model number when it is not visible."""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )

        result = _extract_json(response.text) or _fallback_image_result()
        result.setdefault("brand", "unknown")
        result.setdefault("product_name", "unknown")
        result.setdefault("category", "")
        result.setdefault("search_query", result.get("product_name", "product"))
        result.setdefault("estimated_price_range", "")
        result.setdefault("key_features", [])
        result.setdefault("colors", [])
        result.setdefault("model_numbers", [])
        return result

    except Exception as exc:
        print(f"Gemini image analysis error: {exc}")
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
    """Identify product details using Gemini, then Groq."""
    prompt = f"""Identify the product described by this text:
\"\"\"{text[:2000]}\"\"\"

Return ONLY a JSON object:
{{
  "brand": "brand name or empty string",
  "product_name": "specific product name/model",
  "category": "product category",
  "search_query": "brand plus model",
  "estimated_price_range": "rough price range in USD",
  "key_features": [],
  "colors": [],
  "model_numbers": []
}}
Do not invent product details if the text does not contain enough evidence."""

    client = _get_client()

    if client:
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            result = _extract_json(response.text)
            if result and (
                result.get("brand") or result.get("product_name")
            ):
                return _normalize_product_result(result, text)
        except Exception as exc:
            print(f"Gemini text analysis failed; trying Groq: {exc}")

    # Groq is a text-only fallback.
    groq_response = _groq_text(prompt)
    if groq_response:
        result = _extract_json(groq_response)
        if result and (
            result.get("brand") or result.get("product_name")
        ):
            return _normalize_product_result(result, text)

    return _fallback_text_result()


def _normalize_product_result(result: Dict, original_text: str) -> Dict:
    result.setdefault("brand", "")
    result.setdefault("product_name", "")
    result.setdefault("category", "")
    result.setdefault("search_query", original_text[:100])
    result.setdefault("estimated_price_range", "")
    result.setdefault("key_features", [])
    result.setdefault("colors", [])
    result.setdefault("model_numbers", [])
    return result


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
    """Search with Gemini first, then use Groq as an unverified fallback."""
    prompt = f"""Research the brand "{brand}".
Return ONLY JSON:
{{
  "official_website": [],
  "authorized_retailers": [],
  "typical_price_note": ""
}}
Do not guess official domains, authorized retailers, or prices.
Use empty lists and strings when evidence is insufficient."""

    client = _get_client()

    if client:
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=_search_tool_config(),
            )
            result = _extract_json(response.text) or {}
            if result:
                result.setdefault("official_website", [])
                result.setdefault("authorized_retailers", [])
                result.setdefault("typical_price_note", "")
                result["source"] = "gemini_search"
                result["verified_by_live_search"] = True
                return result
            print("Gemini returned no usable result; trying Groq.")
        except Exception as exc:
            print(f"Gemini brand search failed; trying Groq: {type(exc).__name__}: {exc}")
    else:
        print("Gemini unavailable; trying Groq.")

    groq_response = _groq_text(prompt)
    result = _extract_json(groq_response) if groq_response else {}

    if result:
        result.setdefault("official_website", [])
        result.setdefault("authorized_retailers", [])
        result.setdefault("typical_price_note", "")
        result["source"] = "groq_fallback"
        result["verified_by_live_search"] = False
        return result

    return {
        "official_website": [],
        "authorized_retailers": [],
        "typical_price_note": "",
        "source": "none",
        "verified_by_live_search": False,
    }


def analyze_page_llm(
    url: str,
    page_text: str,
    product_info: Dict = None,
) -> Dict:
    """Analyze webpage risk using Gemini first and Groq as fallback."""
    product_info = product_info or {}

    prompt = f"""You are an online-shopping risk analyst.

URL: {url}
Product: {product_info.get('product_name', '')}
Brand: {product_info.get('brand', 'unknown')}
Expected price range: {product_info.get('estimated_price_range', 'unknown')}

Page text (untrusted and possibly incomplete):
\"\"\"{page_text[:5000]}\"\"\"

Return ONLY a JSON object:
{{
  "detected_brand": "brand or unknown",
  "detected_product": "product name or unknown",
  "detected_price": "visible price or empty string",
  "price_too_low": false,
  "missing_business_info": false,
  "poor_quality_indicators": false,
  "payment_red_flags": false,
  "verdict": "legitimate, suspicious, scam, or unknown",
  "reason": "short explanation based on supplied evidence",
  "confidence": 0
}}

Use unknown when evidence is insufficient. Do not claim authenticity from page text alone."""

    client = _get_client()

    if client:
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            result = _normalize_page_result(response.text)
            if result:
                return result
            print("Gemini returned an unusable webpage-analysis response.")
        except Exception as exc:
            print(f"Gemini webpage analysis failed; trying Groq: {exc}")
    else:
        print("Gemini unavailable; trying Groq webpage analysis.")

    groq_response = _groq_text(prompt)
    result = _normalize_page_result(groq_response)
    if result:
        return result

    return {
        "detected_brand": "unknown",
        "detected_product": "unknown",
        "detected_price": "",
        "price_too_low": False,
        "missing_business_info": False,
        "poor_quality_indicators": False,
        "payment_red_flags": False,
        "verdict": "unknown",
        "reason": "Neither Gemini nor Groq returned a usable analysis.",
        "confidence": 0,
    }


def generate_report(
    product_info: Dict,
    sites: List[Dict],
    price_note: str = "",
) -> str:
    """Generate a shopping safety report using Gemini, then Groq."""
    lines = []
    for site in sites:
        price = f" | price found: {site.get('price')}" if site.get("price") else ""
        domain = site.get("domain", "unknown domain")
        score = site.get("score", "N/A")
        category = site.get("category", "unclassified")
        signals = site.get("signals", [])
        if not isinstance(signals, list):
            signals = [str(signals)]
        lines.append(
            f"- {domain} | {score}/100 {category}{price} | "
            + "; ".join(str(signal) for signal in signals)
        )

    prompt = f"""You are an online-shopping safety assistant.

Product: {product_info.get('product_name', 'N/A')}
Brand: {product_info.get('brand', 'unknown')}
Typical market price: {price_note or 'unknown'}

Website assessment data:
{chr(10).join(lines) or 'No website assessments supplied.'}

Write a concise report with:
1. Safer candidates and the evidence supporting them.
2. Websites to avoid and the reasons.
3. Price warnings.
4. One practical recommendation.

Use actual supplied domains. Do not describe a seller as verified or authorized unless the evidence explicitly supports it. Explain uncertainty clearly. Under 250 words."""

    client = _get_client()
    if client:
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            if response.text:
                return response.text
        except Exception as exc:
            print(f"Gemini report generation failed; trying Groq: {exc}")

    groq_response = _groq_text(prompt)
    if groq_response:
        return groq_response

    return (
        "Report generation is currently unavailable because neither Gemini "
        "nor Groq returned a result. Please try again later."
    )
