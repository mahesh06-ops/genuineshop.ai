import streamlit as st
import pipeline
from config import GEMINI_API_KEY, SAFE_BROWSING_API_KEY

st.set_page_config(page_title="GenuineShop AI", page_icon="🛡️", layout="wide")
st.title("🛡️ GenuineShop AI")
st.caption("Works with ANY product or website — verified live against Wikidata, Google Search, "
           "Google Safe Browsing, actual page content, and WHOIS.")

if not GEMINI_API_KEY:
    st.error("⚠️ Missing GEMINI_API_KEY. Add it to `.env` (local) or Streamlit Secrets (deployed).")
    st.stop()


@st.cache_resource
def get_engine():
    return pipeline.Engine()


engine = get_engine()

with st.sidebar:
    st.header("🔎 Live data sources")
    st.markdown(f"""
    - **Wikidata** brand registry — 🟢 active
    - **Gemini + Google Search** — 🟢 active
    - **Google Safe Browsing** — {'🟢 active' if SAFE_BROWSING_API_KEY else '⚪ optional (add key)'}
    - **WHOIS / SSL** live checks — 🟢 active
    """)
    st.caption("All results fetched live at query time; cached 1–7 days for speed.")


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
            st.markdown(f":{color}[**{r['category']}**] · **{r['score']}/100** · `{r['domain']}`")
            st.progress(r["score"])
            if r.get("price"):
                st.markdown(f"💰 Price found on page: **{r['price']}**")
            for s in r["signals"]:
                st.markdown(f"- {s}")

    if report:
        st.subheader("🤖 AI Safety Report (based on live data)")
        st.markdown(report)


tab1, tab2, tab3 = st.tabs(["📷 Product Image", "⌨️ Product Name", "🔗 Check a Website"])

with tab1:
    img = st.file_uploader("Upload the product photo from the ad", type=["jpg", "jpeg", "png"])
    if img and st.button("Analyze Product", type="primary", use_container_width=True):
        with st.spinner("Live analysis: identifying product → finding official site live → "
                        "verifying every seller… (40–90 sec first time, fast after caching)"):
            info, results, report, profile = engine.analyze_product(
                image_bytes=img.getvalue(), mime_type=img.type)
        st.success(f"Detected: **{info.get('product_name')}** ({info.get('brand')})")
        if profile.get("official"):
            st.info(f"Official site (live-verified): **{', '.join(profile['official'])}**")
        show_results(results, report)

with tab2:
    name = st.text_input("Product name",
                         placeholder="Any product — e.g. Asics Gel-Kayano 30 / Sony WH-1000XM5 / Dyson Airwrap")
    if name and st.button("Analyze", type="primary", use_container_width=True):
        with st.spinner("Live verification in progress… (40–90 sec first time)"):
            info, results, report, profile = engine.analyze_product(product_name=name)
        if profile.get("official"):
            st.info(f"Official site (live-verified): **{', '.join(profile['official'])}**")
        show_results(results, report)

with tab3:
    url = st.text_input("Paste ANY website URL", placeholder="https://any-website.xyz/product/123")
    hint = st.text_input("Brand (optional — improves accuracy)", placeholder="e.g. Sony")
    if url and st.button("Check Website", type="primary", use_container_width=True):
        with st.spinner("Live checks: Safe Browsing → page content analysis → WHOIS/SSL…"):
            result, ctx = engine.analyze_url(url, brand_hint=hint.strip() or None)
        if ctx.get("brand"):
            st.info(f"Brand detected: **{ctx['brand']}** — official site: "
                    f"{', '.join(ctx['official']) or 'not found'}")
        st.markdown(f"### Verdict: **{result['category']}** — {result['score']}/100")
        st.progress(result["score"])
        if result.get("price"):
            st.markdown(f"💰 Price found on page: **{result['price']}**")
        for s in result["signals"]:
            st.markdown(f"- {s}")