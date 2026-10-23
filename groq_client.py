
"""Groq Cloud fallback for text-based AI analysis."""

from groq import Groq
from config import get_keys

MODEL = "openai/gpt-oss-120b"


def analyze_text(prompt: str):
    """Send a text prompt to Groq; return None if unavailable."""
    keys = get_keys()

    if not keys.has_groq() or not keys.groq:
        print("Groq API key is missing.")
        return None

    try:
        client = Groq(api_key=keys.groq)

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Analyze only the evidence provided. "
                        "Never claim a product is genuine without sufficient evidence."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_completion_tokens=300,
        )

        return response.choices[0].message.content

    except Exception as exc:
        print(f"Groq error: {type(exc).__name__}: {exc}")
        return None
