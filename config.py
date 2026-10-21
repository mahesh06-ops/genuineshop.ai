import os
from dotenv import load_dotenv

load_dotenv()

def _get_gemini_key():
    key = os.getenv("GEMINI_API_KEY")          # local: from .env
    if key:
        return key
    try:                                        # deployed: from Streamlit secrets
        import streamlit as st
        return st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        return ""

GEMINI_API_KEY = _get_gemini_key()