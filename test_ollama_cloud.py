
import os
import tomllib
from ollama import Client

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

api_key = secrets.get("OLLAMA_API_KEY") or os.getenv("OLLAMA_API_KEY")

if not api_key:
    raise RuntimeError("OLLAMA_API_KEY is missing from secrets.toml")

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {api_key}"},
)

response = client.chat(
    model="gemma4:31b",
    messages=[
        {"role": "user", "content": "Reply with: Ollama Cloud connected"}
    ],
)

print(response.message.content)
