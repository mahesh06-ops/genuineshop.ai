import streamlit as st
from pipeline import analyze_image, analyze_name, analyze_url

st.set_page_config(page_title="GenuineShop AI", page_icon="🛡️", layout="wide")
st.title("🛡️ GenuineShop AI — Find REAL Sellers, Avoid Fake Websites")

def _render_product_result(result, image=None):
    p = result["product_info"]
    st.subheader("📦 Product Identified")
    c1, c2 = st.columns([1, 2])
    with c1:
        if image is not None:
            st.image(image, width=250)
    with c2:
        st.markdown(f"**Product:** {p.get('product_name', '—')}")
        st.markdown(f"**Brand:** {p.get('brand') or 'Unknown'}")
        if p.get("estimated_price_range"):
            st.markdown(f"**Normal price:** {p['estimated_price_range']}")

    st.subheader("✅ GENUINE SELLERS — Buy from these exact links")
    for link in result["genuine_links"]:
        icon = "🥇" if link["status"] == "OFFICIAL" else "✅"
        st.markdown(f"{icon} **{link['seller']}**  \n🔗 [Open this link]({link['url']}) — `{link['url']}`")
    if result["genuine_links"]:
        st.link_button("🛒 Go to the Official Website Now",
                       result["genuine_links"][0]["url"], type="primary")

    if result.get("avoid"):
        st.subheader("🚫 FAKE SITES SELLING THIS PRODUCT — DO NOT BUY")
        for a in result["avoid"]:
            if isinstance(a, dict):
                st.markdown(f"❌ **{a['domain']}** — {a['reason']}")
            else:
                st.markdown(f"❌ **{a}** — known scam pattern for this brand")

def _render_url_result(result):
    page, v, p = result["page"], result["verdict"], result["product_info"]
    st.subheader("🔍 Website Check Result")
    c1, c2 = st.columns([1, 2])
    with c1:
        if page.get("image"):
            st.image(page["image"], width=250)
        else:
            st.info("No product image found on this page")
    with c2:
        st.markdown(f"**Link checked:** [{page['url']}]({page['url']})")
        st.markdown(f"**Product on this site:** {p.get('product_name', '—')}")
        st.markdown(f"**Brand:** {p.get('brand') or 'Unknown'}")
        if page.get("price"):
            st.markdown(f"**Price on this site:** {page['price']}")

    if v["label"] == "GENUINE":
        st.success("✅ GENUINE WEBSITE — Safe to buy from here")
    elif v["label"] == "FAKE":
        st.error("❌ FAKE WEBSITE — DO NOT BUY FROM HERE")
    else:
        st.warning("⚠️ NOT VERIFIED — We cannot confirm this site. Play safe, use the official links below.")
    st.markdown("**Why:**")
    for r in v["reasons"]:
        st.markdown(f"• {r}")

    if result.get("real_site"):
        st.success("✅ THE REAL WEBSITE IS 👇")
        st.markdown(f"### 🥇 [{result['real_site']['seller']}]({result['real_site']['url']})")
        st.link_button("🔗 Open the Real Website", result["real_site"]["url"], type="primary")

    if result["genuine_links"]:
        st.subheader("✅ Other genuine sellers for this product")
        for link in result["genuine_links"]:
            st.markdown(f"• **{link['seller']}** — [{link['url']}]({link['url']})")

tab1, tab2, tab3 = st.tabs(["📷 Upload Product Image", "⌨️ Type Product Name", "🔗 Check a Website Link"])

with tab1:
    img = st.file_uploader("Upload the product image (from the ad)", type=["jpg", "jpeg", "png"])
    if img and st.button("Find Genuine Sellers", type="primary", key="b1"):
        with st.spinner("Identifying product & finding real sellers..."):
            result = analyze_image(img.getvalue())
        if result.get("error") == "no_ai":
            st.error("⚠️ Image analysis needs ONE free AI provider:\n\n"
                     "**Option A (easiest):** Free Gemini key from "
                     "[aistudio.google.com](https://aistudio.google.com) — no credit card. "
                     "Put it in `.streamlit/secrets.toml` as `GEMINI_API_KEY`.\n\n"
                     "**Option B:** Install [Ollama](https://ollama.com) and run "
                     "`ollama pull llava` — 100% free & offline.\n\n"
                     "💡 Meanwhile, the **'Type Product Name'** and **'Check a Website Link'** "
                     "tabs work WITHOUT any key.")
        else:
            _render_product_result(result, image=img)

with tab2:
    name = st.text_input("Product name", placeholder="e.g., Nike Air Force 1 / iPhone 15 Pro")
    if name.strip() and st.button("Find Genuine Sellers", type="primary", key="b2"):
        with st.spinner("Finding real sellers..."):
            result = analyze_name(name.strip())
        _render_product_result(result, image=result.get("image"))

with tab3:
    url = st.text_input("Website link to check", placeholder="https://nike-shoes-sale.com/air-force-1")
    if url.strip() and st.button("Check Website", type="primary", key="b3"):
        with st.spinner("Fetching the page & verifying..."):
            result = analyze_url(url.strip())
        _render_url_result(result)