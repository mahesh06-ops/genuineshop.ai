import os
from dotenv import load_dotenv

load_dotenv()

def _get(name):
    key = os.getenv(name)
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get(name, "")
    except Exception:
        return ""

GEMINI_API_KEY = _get("GEMINI_API_KEY")
SAFE_BROWSING_API_KEY = _get("SAFE_BROWSING_API_KEY")   # optional but recommended