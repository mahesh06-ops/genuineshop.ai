import ssl
import socket
import whois
from datetime import datetime
from urllib.parse import urlparse
from difflib import SequenceMatcher

SUSPICIOUS_TLDS = (".xyz", ".top", ".buzz", ".click", ".work", ".loan",
                   ".tk", ".ml", ".cf", ".gq", ".icu", ".cyou")


def get_domain(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return urlparse(url).netloc.lower().replace("www.", ""), url


def matches(domain, domain_list):
    """Exact domain or subdomain match (shop.nike.com matches nike.com)."""
    return any(domain == d or domain.endswith("." + d) for d in domain_list if d)


def domain_age_days(domain):
    try:
        w = whois.whois(domain)
        c = w.creation_date
        if isinstance(c, list):
            c = c[0]
        if c is None:
            return -1
        return (datetime.now() - c.replace(tzinfo=None)).days
    except Exception:
        return -1


def ssl_valid(domain):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=8) as s:
            with ctx.wrap_socket(s, server_hostname=domain) as ss:
                ss.getpeercert()
        return True
    except Exception:
        return False


def typosquat(domain, official_list):
    name = domain.split(".")[0]
    for off in official_list:
        sim = SequenceMatcher(None, name, off.split(".")[0]).ratio()
        if 0.7 < sim < 1.0:
            return {"is_typo": True, "imitates": off, "sim": round(sim, 2)}
    return {"is_typo": False}


def _result(url, domain, score, category, signals, price=None):
    return {"url": url, "domain": domain, "score": score,
            "category": category, "signals": signals, "price": price}


def analyze_site(url, ctx):
    """ctx keys: brand, official, official_confirmed, retailers,
    safe_browsing, page, reports — all from LIVE sources."""
    domain, url = get_domain(url)
    official = [d.lower() for d in (ctx.get("official") or [])]
    confirmed = [d.lower() for d in (ctx.get("official_confirmed") or [])]
    retailers = [d.lower() for d in (ctx.get("retailers") or [])]
    brand = (ctx.get("brand") or "").strip()
    score, signals = 50, []

    # A. Official website (verified LIVE)
    if matches(domain, confirmed):
        return _result(url, domain, 100, "SAFE",
            [f"✅ OFFICIAL website of {brand or 'this brand'} — confirmed by 2 live sources (Wikidata + web search)"])
    if matches(domain, official):
        return _result(url, domain, 97, "SAFE",
            [f"✅ Official website of {brand or 'this brand'} (live lookup)"])
    if matches(domain, retailers):
        score = 85
        signals.append(f"✅ Authorized retailer of {brand or 'this brand'} (live web data)")

    # B. Google Safe Browsing — Google's real-time phishing DB
    sb = ctx.get("safe_browsing")
    if sb is True:
        score -= 60
        signals.append("🚨 FLAGGED by Google Safe Browsing (live phishing/malware database)")
    elif sb is None:
        signals.append("ℹ️ Google Safe Browsing not configured (optional API key)")

    # C. Live page-content analysis
    page = ctx.get("page") or {}
    price = page.get("detected_price") or None
    if page:
        v, reason = page.get("verdict"), page.get("reason", "")
        if v == "scam":
            score -= 45; signals.append(f"🚨 Live page analysis: SCAM — {reason}")
        elif v == "suspicious":
            score -= 18; signals.append(f"⚠️ Live page analysis: suspicious — {reason}")
        elif v == "legitimate":
            score += 12; signals.append(f"✅ Live page analysis: looks legitimate — {reason}")
        if page.get("price_too_low"):
            score -= 15
            signals.append(f"🚨 Price on page ({page.get('detected_price', '?')}) is unrealistically low")
        if page.get("missing_business_info"):
            score -= 10; signals.append("⚠️ No business address / contact / return policy found")
        if page.get("payment_red_flags"):
            score -= 10; signals.append("⚠️ Risky payment methods (bank transfer / crypto / gift cards)")

    # D. Brand impersonation + typosquatting (checked against LIVE official list)
    if brand and brand.lower() in domain and not matches(domain, official + retailers):
        score -= 30
        signals.append(f"🚨 Uses brand name '{brand}' but is NOT an official/authorized site")
    t = typosquat(domain, official)
    if t["is_typo"]:
        score -= 35
        signals.append(f"🚨 Typosquatting — imitates {t['imitates']} ({t['sim']:.0%} similar)")

    # E. Community scam reports
    reps = ctx.get("reports") or []
    if reps:
        score -= min(25, 10 * len(reps))
        signals.append(f"⚠️ {len(reps)} web result(s) flag this domain as scam/fake — e.g. “{reps[0][:70]}”")

    # F. WHOIS domain age (live)
    age = domain_age_days(domain)
    if age == -1:
        score -= 15; signals.append("⚠️ Domain age unknown (WHOIS blocked/private)")
    elif age < 60:
        score -= 30; signals.append(f"🚨 Very new domain — {age} days old (live WHOIS)")
    elif age < 365:
        score -= 12; signals.append(f"⚠️ Young domain — {age} days old (live WHOIS)")
    else:
        score += 10; signals.append(f"✅ Established domain — ~{age // 365} year(s) old (live WHOIS)")

    # G. SSL / TLD / IP (live)
    if ssl_valid(domain):
        score += 5; signals.append("✅ Valid SSL certificate (live check)")
    else:
        score -= 25; signals.append("🚨 No valid SSL certificate (live check)")
    if domain.endswith(SUSPICIOUS_TLDS):
        score -= 20; signals.append("⚠️ TLD commonly abused by scam sites")
    if domain and all(c.isdigit() or c == "." for c in domain):
        score -= 25; signals.append("🚨 URL uses a raw IP address")

    score = max(0, min(100, score))
    category = "SAFE" if score >= 70 else "SUSPICIOUS" if score >= 40 else "DANGEROUS"
    return _result(url, domain, score, category, signals, price)