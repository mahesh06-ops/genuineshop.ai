"""
Vision Module — Multi-provider product identification with validation.
"""
import json
import base64
from config import get_keys

IMAGE_PROMPT = (
    "Analyze this product image. Return ONLY valid JSON, nothing else: "
    '{"brand": "brand name or empty string", "product_name": "specific product name", '
    '"category": "product category", "search_query": "short search phrase: brand + model", '
    '"estimated_price_range": "e.g. $90 - $115", "key_features": [], "colors": [], "model_numbers": []}'
)

TEXT_PROMPT = (
    'Website/product text:\n"{text}"\n\n'
    "What product is being sold? Return ONLY valid JSON: "
    '{"brand": "", "product_name": "", "category": "", "search_query": "", '
    '"estimated_price_range": "e.g. $90 - $115", "key_features": [], "colors": [], "model_numbers": []}'
)


def _clean_json(text: str) -> dict:
    """LLMs sometimes wrap JSON in ``` fences — strip them safely."""
    text = (text or "").strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.lower().startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e+1])
        except Exception:
            pass
    return {}


# ---------- Provider 1: Google Gemini (FREE key, supports images + grounding) ----------
def _gemini(prompt: str, image_bytes: bytes = None) -> dict:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=get_keys().gemini)

    parts = []
    if image_bytes:
        mime = "image/png" if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    parts.append(prompt)

    resp = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _clean_json(resp.text)


# ---------- Provider 2: Ollama Cloud ----------
def _ollama_cloud(prompt: str, image_bytes: bytes = None) -> dict:
    import ollama

    api_key = get_keys().ollama_cloud
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not configured")

    client = ollama.Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    model = "llava:latest" if image_bytes else "gemma4:31b"
    message = {"role": "user", "content": prompt}
    if image_bytes:
        message["images"] = [base64.b64encode(image_bytes).decode()]

    response = client.chat(model=model, messages=[message])
    return _clean_json(response.message.content)


# ---------- Provider 3: Local Ollama ----------
def _ollama_local(prompt: str, image_bytes: bytes = None) -> dict:
    import ollama

    model = "llava:latest" if image_bytes else "llama3.2:latest"
    message = {"role": "user", "content": prompt}
    if image_bytes:
        message["images"] = [base64.b64encode(image_bytes).decode()]

    response = ollama.chat(model=model, messages=[message])
    return _clean_json(response.message.content)


# ---------- Provider 4: Groq (Text-only, Fast, Free) ----------
def _groq(prompt: str) -> dict:
    from groq import Groq
    client = Groq(api_key=get_keys().groq)
    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


# ---------- Public Functions ----------

def identify_product_from_image(image_bytes: bytes) -> Optional[dict]:
    """Identify a product from an uploaded image with provider fallback."""
    keys = get_keys()

    # 1. Gemini (best for images + free)
    if keys.has_gemini():
        try:
            result = _gemini(IMAGE_PROMPT, image_bytes)
            if result.get("brand") or result.get("product_name"):
                return result
        except Exception as exc:
            print(f"Gemini image analysis failed: {exc}")

    # 2. Ollama Cloud (if configured)
    if keys.has_ollama_cloud():
        try:
            result = _ollama_cloud(IMAGE_PROMPT, image_bytes)
            if result.get("brand") or result.get("product_name"):
                return result
        except Exception as exc:
            print(f"Ollama Cloud image analysis failed: {exc}")

    # 3. Local Ollama (if running)
    try:
        result = _ollama_local(IMAGE_PROMPT, image_bytes)
        if result.get("brand") or result.get("product_name"):
            return result
    except Exception as exc:
        print(f"Local Ollama image analysis failed: {exc}")

    return None


def identify_product_from_text(text: str) -> Optional[dict]:
    """Extract product details from text with provider fallback."""
    prompt = TEXT_PROMPT.format(text=text[:2000])
    keys = get_keys()

    # 1. Gemini
    if keys.has_gemini():
        try:
            result = _gemini(prompt)
            if result.get("brand") or result.get("product_name"):
                return result
        except Exception as exc:
            print(f"Gemini text analysis failed: {exc}")

    # 2. Groq (fast, free, text-only)
    if keys.groq:
        try:
            result = _groq(prompt)
            if result.get("brand") or result.get("product_name"):
                return result
        except Exception as exc:
            print(f"Groq text analysis failed: {exc}")

    # 3. Ollama Cloud
    if keys.has_ollama_cloud():
        try:
            result = _ollama_cloud(prompt)
            if result.get("brand") or result.get("product_name"):
                return result
        except Exception as exc:
            print(f"Ollama Cloud text analysis failed: {exc}")

    # 4. Local Ollama
    try:
        result = _ollama_local(prompt)
        if result.get("brand") or result.get("product_name"):
            return result
    except Exception as exc:
        print(f"Local Ollama text analysis failed: {exc}")

    return None