import re, ssl, socket, whois
from datetime import datetime, date
from urllib.parse import urlparse
from difflib import SequenceMatcher

SUSPICIOUS_TLDS = (".xyz", ".top", ".buzz", ".click", ".work", ".shop", ".store",
                   ".online", ".site", ".icu", ".live", ".rest", ".monster")

class WebsiteVerifier:

    def get_domain_info(self, url: str) -> dict:
        if "://" not in url:
            url = "https://" + url
        domain = urlparse(url).netloc.split(":")[0]
        domain = domain[4:] if domain.startswith("www.") else domain
        return {"domain": domain,
                "domain_age_days": self._domain_age(domain),
                "ssl_valid": self._check_ssl(domain),
                "is_ip_address": self._is_ip_url(url),
                "has_suspicious_tld": any(domain.endswith(t) for t in SUSPICIOUS_TLDS)}

    def _domain_age(self, domain):
        try:
            c = whois.whois(domain).creation_date
            if isinstance(c, list): c = c[0]
            if c is None: return -1
            if isinstance(c, datetime):
                if c.tzinfo: c = c.replace(tzinfo=None)
            elif isinstance(c, date):
                c = datetime(c.year, c.month, c.day)
            return (datetime.now() - c).days
        except Exception:
            return -1

    def _check_ssl(self, domain):
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=domain):
                    return True
        except Exception:
            return False

    def _is_ip_url(self, url):
        host = urlparse(url).netloc.split(":")[0]
        parts = host.split(".")
        return len(parts) == 4 and all(p.isdigit() for p in parts)

    def detect_typosquatting(self, url, official_domains):
        if "://" not in url: url = "https://" + url
        first = urlparse(url).netloc.split(":")[0]
        first = first[4:] if first.startswith("www.") else first
        first = first.split(".")[0]
        for official in official_domains:
            sim = SequenceMatcher(None, first, official.split(".")[0]).ratio()
            if 0.75 < sim < 1.0:
                return {"is_typosquat": True, "imitating": official, "similarity": round(sim, 2)}
        return {"is_typosquat": False}

    # ---------- price sanity ----------
    @staticmethod
    def _first_number(s):
        if not s: return None
        m = re.search(r"\d+(?:\.\d{1,2})?", str(s).replace(",", ""))
        return float(m.group()) if m else None

    @staticmethod
    def _numbers(s):
        if not s: return []
        return [float(m) for m in re.findall(r"\d+(?:\.\d{1,2})?", str(s).replace(",", ""))]

    def price_suspicion(self, page_price, est_range):
        p = self._first_number(page_price)
        nums = self._numbers(est_range)
        if p is not None and nums:
            low = min(nums)
            if low > 0 and p < 0.5 * low:
                pct = int((1 - p / low) * 100)
                return f"Price ({page_price}) is ~{pct}% BELOW the normal price (~{low:.0f})"
        return None

    # ---------- decisive verdict ----------
    def decide(self, url, rag_match, official_domains, page_price=None, est_price_range=None):
        info = self.get_domain_info(url)
        reasons, red = [], 0

        if rag_match["status"] == "official":
            reasons.append(rag_match["reason"])
            if info["ssl_valid"]: reasons.append("Valid SSL certificate")
            if info["domain_age_days"] > 365:
                reasons.append(f"Domain is {info['domain_age_days']//365}+ years old")
            return {"label": "GENUINE", "kind": "official", "reasons": reasons}

        if rag_match["status"] == "authorized":
            reasons.append(rag_match["reason"])
            return {"label": "GENUINE", "kind": "authorized", "reasons": reasons}

        if rag_match["status"] == "scam_pattern":
            red += 3; reasons.append(rag_match["reason"])
        if rag_match["status"] == "impersonation":
            red += 2; reasons.append(rag_match["reason"])

        typo = self.detect_typosquatting(url, official_domains)
        if typo.get("is_typosquat"):
            red += 3; reasons.append(f"Lookalike domain imitating {typo['imitating']} (typosquatting)")

        if info["is_ip_address"]:
            red += 3; reasons.append("Uses an IP address instead of a real domain name")
        if info["domain_age_days"] == -1:
            red += 1; reasons.append("Domain age could not be verified")
        elif info["domain_age_days"] < 90:
            red += 2; reasons.append(f"Domain is only {info['domain_age_days']} days old — scam sites are usually brand new")
        elif info["domain_age_days"] > 730:
            reasons.append(f"Domain is {info['domain_age_days']//365} years old")
        if not info["ssl_valid"]:
            red += 1; reasons.append("Invalid or missing SSL certificate (not secure)")
        if info["has_suspicious_tld"]:
            red += 1; reasons.append(f"Uses a suspicious TLD (.{url.split('.')[-1]})")

        flag = self.price_suspicion(page_price, est_price_range)
        if flag:
            red += 2; reasons.append(flag)

        if red >= 2:
            return {"label": "FAKE", "kind": rag_match["status"], "reasons": reasons}
        return {"label": "UNVERIFIED", "kind": "unknown",
                "reasons": reasons or ["Not in the verified database — no strong signals either way"]}