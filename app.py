import streamlit as st
from pipeline import analyze_image, analyze_name, analyze_url

st.set_page_config(page_title="GenuineShop AI", page_icon="🛒", layout="wide")
st.title("🛒 GenuineShop AI — Find REAL Sellers, Avoid Fake Websites")

# Feature status sidebar
with st.sidebar:
    st.header("🔧 System Status")
    from config import features_enabled
    feats = features_enabled()
    for name, enabled in feats.items():
        status = "✅" if enabled else "❌"
        st.write(f"{status} {name.replace('_', ' ').title()}")
    st.divider()
    st.caption("Add API keys in `.streamlit/secrets.toml` to enable features")


def _render_availability_badge(avail: dict) -> str:
    """Render availability as colored badge."""
    if avail is None:
        return "`Unknown`"
    if avail.get("available") is True:
        return "✅ **In Stock**"
    elif avail.get("available") is False:
        return "❌ **Out of Stock / Unavailable**"
    else:
        conf = avail.get("confidence", 0)
        if conf > 60:
            return "✅ **Likely Available**"
        elif conf > 30:
            return "⚠️ **Uncertain**"
        else:
            return "❓ **Unknown**"


def _render_product_result(result: dict, image=None):
    p = result["product_info"]
    st.subheader("📦 Product Identified")
    c1, c2 = st.columns([1, 2])
    with c1:
        if image is not None:
            st.image(image, width=250)
        elif p.get("image"):
            st.image(p["image"], width=250)
    with c2:
        st.markdown(f"**Product:** {p.get('product_name', '—')}")
        st.markdown(f"**Brand:** {p.get('brand') or 'Unknown'}")
        if p.get("estimated_price_range"):
            st.markdown(f"**Typical Price:** {p['estimated_price_range']}")
        if p.get("key_features"):
            st.markdown(f"**Features:** {', '.join(p['key_features'][:5])}")

    st.subheader("✅ GENUINE SELLERS — Buy from these exact links")
    if not result["genuine_links"]:
        st.warning("No verified sellers found. Try searching manually on official brand site.")
    else:
        for i, link in enumerate(result["genuine_links"]):
            icon = "🥇" if link["status"] == "OFFICIAL" else "✅" if link["status"] == "AUTHORIZED" else "🏪"
            avail_badge = _render_availability_badge(link.get("availability"))
            with st.container():
                st.markdown(f"{icon} **{link['seller']}** {avail_badge}")
                st.markdown(f"🔗 [Open this link]({link['url']}) — `{link['url']}`")
                if link.get("snippet"):
                    st.caption(link["snippet"][:200])
                st.divider()

        # Primary CTA button
        official_links = [l for l in result["genuine_links"] if l["status"] == "OFFICIAL"]
        if official_links:
            st.link_button("🛒 Go to Official Website Now", official_links[0]["url"], type="primary")
        elif result["genuine_links"]:
            st.link_button("🛒 Go to Best Verified Seller", result["genuine_links"][0]["url"], type="primary")

    if result.get("avoid"):
        st.subheader("🚫 FAKE SITES SELLING THIS PRODUCT — DO NOT BUY")
        for a in result["avoid"]:
            if isinstance(a, dict):
                st.markdown(f"❌ **{a['domain']}** — {a['reason']}")
                if a.get("url"):
                    st.caption(f"URL: {a['url']}")
            else:
                st.markdown(f"❌ **{a}** — known scam pattern for this brand")


def _render_url_result(result: dict):
    page, v, p = result["page"], result["verdict"], result["product_info"]
    label = v["label"]

    st.subheader("🔍 Website Check Result")

    # Verdict banner
    if label == "GENUINE":
        st.success(f"✅ **{label} WEBSITE** — Safe to buy from here")
    elif label == "FAKE":
        st.error(f"❌ **{label} WEBSITE** — DO NOT BUY FROM HERE")
    else:
        st.warning(f"⚠️ **{label}** — We cannot confirm this site. Play safe, use official links below.")

    # Reasons
    st.markdown("**Analysis:**")
    for r in v["reasons"]:
        st.markdown(f"• {r}")

    # Score breakdown
    if "net_score" in v:
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Trust Signals", v.get("green_score", 0))
        c2.metric("🔴 Risk Signals", v.get("red_score", 0))
        c3.metric("📊 Net Score", v.get("net_score", 0))

    # Page preview
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

    # Real official site
    if result.get("real_site"):
        rs = result["real_site"]
        st.success("✅ **THE REAL WEBSITE IS 👇**")
        avail = rs.get("availability")
        if avail:
            st.markdown(f"Availability: {_render_availability_badge(avail)}")
        st.markdown(f"### 🥇 [{rs['seller']}]({rs['url']})")
        st.link_button("🔗 Open the Real Website", rs["url"], type="primary")

    # Other genuine sellers
    if result["genuine_links"]:
        st.subheader("✅ Other Verified Sellers for This Product")
        for link in result["genuine_links"]:
            if link["status"] == "OFFICIAL" and result.get("real_site"):
                continue  # Already shown
            avail_badge = _render_availability_badge(link.get("availability"))
            st.markdown(f"• **{link['seller']}** {avail_badge} — [{link['url']}]({link['url']})")


# ---------- TABS ----------
tab1, tab2, tab3 = st.tabs(["📷 Upload Product Image", "⌨️ Type Product Name", "🔗 Check a Website Link"])

with tab1:
    st.markdown("Upload a product photo (from an ad, screenshot, or photo) to identify it and find genuine sellers.")
    img = st.file_uploader("Upload product image", type=["jpg", "jpeg", "png"], key="img_upload")
    if img and st.button("Find Genuine Sellers", type="primary", key="b1"):
        with st.spinner("Identifying product & finding real sellers..."):
            result = analyze_image(img.getvalue())
        if result.get("error") == "no_ai":
            st.error("⚠️ **Image analysis needs an AI provider**\n\n"
                     "**Option A (Recommended):** Get a free Gemini API key from "
                     "[Google AI Studio](https://aistudio.google.com) — no credit card needed. "
                     "Add it to `.streamlit/secrets.toml` as `GEMINI_API_KEY`.\n\n"
                     "**Option B:** Install [Ollama](https://ollama.com) locally and run "
                     "`ollama pull llava` — 100% free & offline.\n\n"
                     "💡 Meanwhile, the **'Type Product Name'** and **'Check a Website Link'** "
                     "tabs work WITHOUT any API key.")
        else:
            _render_product_result(result, image=img)

with tab2:
    st.markdown("Enter a product name (e.g., 'Nike Air Force 1', 'iPhone 15 Pro', 'Sony WH-1000XM5')")
    name = st.text_input("Product name", placeholder="e.g., Nike Air Force 1 / iPhone 15 Pro", key="name_input")
    if name.strip() and st.button("Find Genuine Sellers", type="primary", key="b2"):
        with st.spinner("Finding real sellers..."):
            result = analyze_name(name.strip())
        _render_product_result(result, image=result.get("image"))

with tab3:
    st.markdown("Paste any product page URL to check if it's genuine or fake.")
    url = st.text_input("Website link to check", placeholder="https://nike-shoes-sale.com/air-force-1", key="url_input")
    if url.strip() and st.button("Check Website", type="primary", key="b3"):
        with st.spinner("Fetching the page & verifying with real-time security data..."):
            result = analyze_url(url.strip())
        _render_url_result(result)