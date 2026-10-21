import streamlit as st
import pipeline
from config import GEMINI_API_KEY

st.set_page_config(page_title="GenuineShop AI", page_icon="🛡️", layout="wide")
st.title("🛡️ GenuineShop AI")
st.caption("Saw a product ad? Verify the seller before you buy — we find genuine websites and flag fake ones.")

if not GEMINI_API_KEY:
    st.error("⚠️ Missing GEMINI_API_KEY. Add it to `.env` (local) or Streamlit Secrets (deployed).")
    st.stop()

@st.cache_resource
def get_engine():
    return pipeline.Engine()

engine = get_engine()

def show_results(results, report=None):
    safe = sum(1 for r in results if r["category"] == "SAFE")
    sus = sum(1 for r in results if r["category"] == "SUSPICIOUS")
    bad = sum(1 for r in results if r["category"] == "DANGEROUS")
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Safe Sellers", safe)
    c2.metric("⚠️ Suspicious", sus)
    c3.metric("🚨 Dangerous", bad)

    for r in results:
        color = {"SAFE": "green", "SUSPICIOUS": "orange", "DANGEROUS": "red"}[r["category"]]
        with st.container(border=True):
            st.markdown(f":{color}[**{r['category']}**]  ·  **{r['score']}/100**  ·  `{r['domain']}`")
            st.progress(r["score"])
            for s in r["signals"]:
                st.markdown(f"- {s}")

    if report:
        st.subheader("🤖 AI Safety Report")
        st.markdown(report)

tab1, tab2, tab3 = st.tabs(["📷 Product Image", "⌨️ Product Name", "🔗 Check a Website"])

with tab1:
    img = st.file_uploader("Upload the product photo from the ad", type=["jpg", "jpeg", "png"])
    if img and st.button("Analyze Product", type="primary", use_container_width=True):
        with st.spinner("Identifying product → searching sellers → verifying websites… (30–60 sec)"):
            info, results, report = engine.analyze_product(
                image_bytes=img.getvalue(), mime_type=img.type)
        st.success(f"Detected: **{info.get('product_name')}** ({info.get('brand')}) — typical price: {info.get('typical_price_range', 'N/A')}")
        show_results(results, report)

with tab2:
    name = st.text_input("Product name", placeholder="e.g. Nike Air Force 1 / iPhone 15 / boAt Airdopes 141")
    if name and st.button("Analyze", type="primary", use_container_width=True):
        with st.spinner("Searching and verifying sellers…"):
            info, results, report = engine.analyze_product(product_name=name)
        show_results(results, report)

with tab3:
    url = st.text_input("Paste the website URL from the ad",
                        placeholder="https://example-shop.xyz/product/123")
    if url and st.button("Check Website", type="primary", use_container_width=True):
        with st.spinner("Running verification checks…"):
            result, rag = engine.analyze_url(url)
        st.markdown(f"### Verdict: **{result['category']}** — {result['score']}/100")
        st.progress(result["score"])
        for s in result["signals"]:
            st.markdown(f"- {s}")
        if rag.get("status") == "official":
            st.success("This is the official brand website. Safe to buy. ✅")
        elif rag.get("status") == "retailer":
            st.success("This is an authorized retailer in our database. Generally safe. ✅")
        else:
            st.warning("⚠️ Not in our verified database. If the price looks too good to be true, it probably is. Buy from the official site instead.")