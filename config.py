import os

def get_key(name: str):
    """Read an API key from environment variable or .streamlit/secrets.toml."""
    v = os.environ.get(name)
    if v:
        return v
    try:
        import tomllib                     # Python 3.11+
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f).get(name)
    except Exception:
        return None
import os

def _get_secret(name):
    value = os.getenv(name)
    if value:
        return value

    try:
        import tomllib
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f).get(name)
    except (OSError, ValueError, ImportError):
        return None

SAFE_BROWSING_API_KEY = _get_secret("SAFE_BROWSING_API_KEY")