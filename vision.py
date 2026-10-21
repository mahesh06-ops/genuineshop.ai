import json
from config import get_key

IMAGE_PROMPT = (
    "Analyze this product image. Return ONLY valid JSON, nothing else: "
    '{"brand": "brand name or empty string", "product_name": "specific product name", '
    '"category": "product category", "search_query": "short search phrase: brand + model", '
    '"estimated_price_range": "e.g. $90 - $115"}'
)

TEXT_PROMPT = (
    'Website/product text:\n"{text}"\n\n'
    "What product is being sold? Return ONLY valid JSON: "
    '{"brand": "", "product_name": "", "search_query": "", '
    '"estimated_price_range": "e.g. $90 - $115"}'
)


def _clean_json(text: str) -> dict:
    """LLMs sometimes wrap JSON in ``` fences — strip them safely."""
    text = (text or "").strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.lower().startswith("json"):
            text = text[4:]
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


# ---------- Provider 1: Google Gemini (FREE key, supports images) ----------
def _gemini(prompt: str, image_bytes: bytes = None) -> dict:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=get_key("GEMINI_API_KEY"))
    parts = []
    if image_bytes:
        mime = "image/png" if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    parts.append(prompt)
    resp = client.models.generate_content(
        model="gemini-3.8-flash",                 # free tier model
        contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _clean_json(resp.text)


# ---------- Provider 3: Ollama Cloud ----------
def _ollama_cloud(prompt: str, image_bytes: bytes = None) -> dict:
    import ollama

    api_key = get_key("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not configured")

    client = ollama.Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    # Use a vision-capable cloud model for image requests.
    # Use the text model that succeeded in your connection test otherwise.
    model =  "gemma4:31b-cloud" if image_bytes else "gemma4:31b"

    message = {"role": "user", "content": prompt}
    if image_bytes:
        message["images"] = [image_bytes]

    response = client.chat(model=model, messages=[message])
    return _clean_json(response.message.content)


# ---------- Provider 4: Local Ollama fallback ----------
def _ollama(prompt: str, image_bytes: bytes = None) -> dict:
    import ollama

    model = "llava" if image_bytes else "llama3.2"
    message = {"role": "user", "content": prompt}

    if image_bytes:
        message["images"] = [image_bytes]

    response = ollama.chat(model=model, messages=[message])
    return _clean_json(response.message.content)

# ---------- Public functions used by pipeline.py ----------

def identify_product_from_image(image_bytes: bytes):
    """Identify a product from an uploaded image."""
    if get_key("GEMINI_API_KEY"):
        try:
            return _gemini(IMAGE_PROMPT, image_bytes)
        except Exception as exc:
            print(f"Gemini image analysis failed: {exc}")

    if get_key("OLLAMA_API_KEY"):
        try:
            return _ollama_cloud(IMAGE_PROMPT, image_bytes)
        except Exception as exc:
            print(f"Ollama Cloud image analysis failed: {exc}")

    # Local fallback, if the model is installed.
    try:
        return _ollama(IMAGE_PROMPT, image_bytes)
    except Exception as exc:
        print(f"Local Ollama image analysis failed: {exc}")
        return None


def identify_product_from_text(text: str):
    """Extract product details from text."""
    prompt = TEXT_PROMPT.format(text=text[:1500])

    if get_key("GEMINI_API_KEY"):
        try:
            return _gemini(prompt)
        except Exception as exc:
            print(f"Gemini text analysis failed: {exc}")

    if get_key("GROQ_API_KEY"):
        try:
            return _groq(prompt)
        except Exception as exc:
            print(f"Groq text analysis failed: {exc}")

    if get_key("OLLAMA_API_KEY"):
        try:
            return _ollama_cloud(prompt)
        except Exception as exc:
            print(f"Ollama Cloud text analysis failed: {exc}")

    try:
        return _ollama(prompt)
    except Exception as exc:
        print(f"Local Ollama text analysis failed: {exc}")
        return None
