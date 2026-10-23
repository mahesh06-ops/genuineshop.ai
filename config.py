
"""Centralized configuration with free API key management."""

import os
import tomllib
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


# Resolve paths relative to this file, not the terminal's working directory.
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
SECRETS_FILE = BASE_DIR / ".streamlit" / "secrets.toml"

# Load environment variables from the project's .env file.
load_dotenv(ENV_FILE)


@dataclass
class APIKeys:
    """API keys loaded from environment variables or Streamlit secrets."""

    gemini: Optional[str] = None
    safe_browsing: Optional[str] = None
    virustotal: Optional[str] = None
    google_cse_key: Optional[str] = None
    google_cse_cx: Optional[str] = None
    serpapi: Optional[str] = None
    groq: Optional[str] = None
    ollama_cloud: Optional[str] = None

    def __post_init__(self):
        self._load_from_env_or_secrets()

    def _load_from_env_or_secrets(self):
        secrets = self._read_secrets()

        # Python field name -> accepted environment/secrets names.
        env_names = {
            "gemini": ["GEMINI_API_KEY", "GEMINI"],
            "safe_browsing": [
                "SAFE_BROWSING_API_KEY", "SAFE_BROWSING"
            ],
            "virustotal": ["VIRUSTOTAL_API_KEY", "VIRUSTOTAL"],
            "google_cse_key": [
                "GOOGLE_CSE_API_KEY", "GOOGLE_CSE_KEY"
            ],
            "google_cse_cx": [
                "GOOGLE_CSE_CX", "GOOGLE_CSE_CX_ID"
            ],
            "serpapi": ["SERPAPI_KEY", "SERPAPI"],
            "groq": ["GROQ_API_KEY", "GROQ"],
            "ollama_cloud": [
                "OLLAMA_API_KEY",
                "OLLAMA_CLOUD_API_KEY",
                "OLLAMA_CLOUD",
            ],
        }

        for field, names in env_names.items():
            value = None

            # Environment variables take priority.
            for name in names:
                candidate = os.getenv(name)
                if candidate and candidate.strip():
                    value = candidate.strip()
                    break

            # Fall back to Streamlit secrets.
            if not value:
                for name in names:
                    candidate = secrets.get(name)
                    if isinstance(candidate, str) and candidate.strip():
                        value = candidate.strip()
                        break

            if value:
                setattr(self, field, value)

    @staticmethod
    def _read_secrets() -> dict:
        try:
            with SECRETS_FILE.open("rb") as file:
                data = tomllib.load(file)

            # Support both top-level secrets and [default] sections.
            default_section = data.get("default", {})
            if isinstance(default_section, dict):
                return {**default_section, **data}

            return data
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def has_gemini(self) -> bool:
        return bool(self.gemini)

    def has_safe_browsing(self) -> bool:
        return bool(self.safe_browsing)

    def has_virustotal(self) -> bool:
        return bool(self.virustotal)

    def has_google_cse(self) -> bool:
        return bool(self.google_cse_key and self.google_cse_cx)

    def has_groq(self) -> bool:
        return bool(self.groq)

    def has_ollama_cloud(self) -> bool:
        return bool(self.ollama_cloud)


@lru_cache(maxsize=1)
def get_keys() -> APIKeys:
    """Return the cached API key configuration."""
    return APIKeys()


def features_enabled() -> dict:
    """Return feature availability based on configured credentials."""
    keys = get_keys()

    return {
        "gemini_grounded_search": keys.has_gemini(),
        "safe_browsing": keys.has_safe_browsing(),
        "virustotal_reputation": keys.has_virustotal(),
        "official_product_search": keys.has_google_cse(),
        "serpapi_fallback": bool(keys.serpapi),
        "groq_text_model": keys.has_groq(),
        "ollama_cloud": keys.has_ollama_cloud(),
    }


# Cache and request configuration
CACHE_TTL_DAYS = 7
PAGE_CACHE_TTL_HOURS = 24
REPUTATION_CACHE_TTL_HOURS = 24
MAX_PAGE_CHARS = 6000
REQUEST_TIMEOUT = 15

# Suspicious top-level domains
SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".buzz", ".click", ".work", ".shop", ".store",
    ".online", ".site", ".icu", ".live", ".rest", ".monster",
    ".club", ".fun", ".space", ".website", ".tech", ".info",
    ".biz", ".cc", ".tk", ".ml", ".ga", ".cf", ".gq",
}

# Trusted marketplace domains
TRUSTED_MARKETPLACES = {
    "amazon.com", "amazon.in", "amazon.co.uk", "amazon.de",
    "flipkart.com", "myntra.com", "footlocker.com",
    "walmart.com", "bestbuy.com", "target.com", "croma.com",
    "reliancedigital.in", "vijaysales.com", "poorvika.com",
}

# Search result cache file
CACHE_FILE = str(BASE_DIR / "search_cache.json")
