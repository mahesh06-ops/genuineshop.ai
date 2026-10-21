import json
from google import genai
from google.genai import types
from config import GEMINI_API_KEY

MODEL = "gemini-2.0-flash"
client = genai.Client(api_key=GEMINI_API_KEY)

def identify_product_from_image(image_bytes, mime_type="image/jpeg"):
    prompt = """Analyze this product image (likely from an online ad).
Return ONLY valid JSON with these keys:
{"brand": "brand name or 'unknown'", "product_name": "specific product name",
 "category": "product category", "search_query": "good search query to find sellers",
 "typical_price_range": "rough price range in USD or INR"}"""
    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        return json.loads(resp.text)
    except Exception:
        return {"brand": "unknown", "product_name": "unknown",
                "category": "", "search_query": "product", "typical_price_range": ""}

def generate_report(product_info, sites):
    lines = "\n".join(
        f"- {s['domain']} | score {s['score']}/100 | {s['category']} | "
        f"{'; '.join(s['signals'])}"
        for s in sites
    )
    prompt = f"""You are an online shopping safety expert helping people avoid scam websites.
Product searched: {product_info.get('product_name', 'N/A')} (brand: {product_info.get('brand', 'unknown')})
Website analysis results:
{lines}

Write a clear, decisive safety report with these sections:
1. **✅ Safe to buy from** — list genuine sites with reasons
2. **🚨 Avoid** — list dangerous/suspicious sites with reasons
3. **⚠️ Red flags noticed** — price too low, payment methods, urgency tactics, etc.
4. **💡 Best recommendation** — the single best place to buy and one safety tip

Keep it under 250 words. Use simple language."""
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    return resp.text