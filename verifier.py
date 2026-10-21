import ssl
import socket
import whois
from datetime import datetime
from urllib.parse import urlparse
from difflib import SequenceMatcher

SUSPICIOUS_TLDS = (".xyz", ".top", ".buzz", ".click", ".work", ".loan", ".tk", ".ml", ".cf", ".gq")

def get_domain(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return urlparse(url).netloc.lower().replace("www.", ""), url

def domain_age_days(domain):
    """Scam sites are usually days old. -1 = unknown."""
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
    """Detect lookalikes: amaz0n.com, nikke.com, amazonn.com"""
    name = domain.split(".")[0]
    for off in official_list:
        oname = off.split(".")[0]
        sim = SequenceMatcher(None, name, oname).ratio()
        if 0.7 < sim < 1.0:
            return {"is_typo": True, "imitates": off, "sim": round(sim, 2)}
    return {"is_typo": False}

def analyze_site(url, rag):
    """Combine all signals into a 0-100 trust score."""
    domain, url = get_domain(url)
    score = 50
    signals = []
    status = rag.get("status", "unknown")
    official = rag.get("official", [])
    brand = rag.get("brand", "")

    # --- Knowledge base verdicts (highest weight) ---
    if status == "official":
        return {"url": url, "domain": domain, "score": 100, "category": "SAFE",
                "signals": [f"✅ Official website of {brand} (verified in database)"]}
    if status == "retailer":
        score = 85
        signals.append(f"✅ Authorized retailer of {brand} (verified in database)")
    if status == "scam":
        score -= 55
        signals.append("🚨 Domain matches a known scam pattern in our database")

    # --- Brand impersonation: contains brand name but isn't official ---
    if status not in ("official", "retailer") and brand and brand.lower() in domain:
        score -= 30
        signals.append(f"🚨 Contains brand name '{brand}' but is NOT an official/authorized site")

    # --- Typosquatting ---
    t = typosquat(domain, official)
    if t["is_typo"]:
        score -= 35
        signals.append(f"🚨 Typosquatting — imitates {t['imitates']} ({t['sim']:.0%} similar)")

    # --- Domain age (WHOIS) ---
    age = domain_age_days(domain)
    if age == -1:
        score -= 15
        signals.append("⚠️ Domain age unknown (WHOIS blocked or private)")
    elif age < 60:
        score -= 30
        signals.append(f"🚨 Very new domain — only {age} days old")
    elif age < 365:
        score -= 12
        signals.append(f"⚠️ Young domain — {age} days old")
    else:
        score += 10
        signals.append(f"✅ Established domain — ~{age // 365} year(s) old")

    # --- SSL certificate ---
    if ssl_valid(domain):
        score += 5
        signals.append("✅ Valid SSL (HTTPS) certificate")
    else:
        score -= 25
        signals.append("🚨 No valid SSL certificate")

    # --- Suspicious TLD ---
    if domain.endswith(SUSPICIOUS_TLDS):
        score -= 20
        signals.append("⚠️ Suspicious TLD commonly used by scam sites")

    # --- Raw IP address URL ---
    if domain and all(ch.isdigit() or ch == "." for ch in domain):
        score -= 25
        signals.append("🚨 URL uses a raw IP address instead of a domain name")

    score = max(0, min(100, score))
    category = "SAFE" if score >= 70 else "SUSPICIOUS" if score >= 40 else "DANGEROUS"
    return {"url": url, "domain": domain, "score": score,
            "category": category, "signals": signals}