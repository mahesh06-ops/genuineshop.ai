"""
Advanced Website Verifier — Multi-signal fake detection with weighted scoring.
"""
import re, ssl, socket, whois
from datetime import datetime, date
from urllib.parse import urlparse
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from config import get_keys, SUSPICIOUS_TLDS
from live_lookup import (
    safe_browsing_check,
    virustotal_reputation,
    urlvoid_scan,
    domain_intelligence,
    community_scam_reports,
)

# Expanded suspicious patterns
SUSPICIOUS_KEYWORDS = [
    "clearance", "outlet", "factory", "wholesale", "liquidation",
    "discount", "cheap", "sale", "offer", "deal", "limited",
    "flash", "mega", "super", "best", "top", "official",
    "authentic", "genuine", "original", "direct", "store"
]

BRAND_IMPERSONATION_PATTERNS = [
    r"(official|authentic|genuine|original)-?{brand}",
    r"{brand}-?(shop|store|outlet|sale|discount|deal)",
    r"buy-?{brand}-?(online|cheap|discount)",
    r"{brand}-?(factory|warehouse|clearance)",
]


class WebsiteVerifier:

    def get_domain_info(self, url: str) -> Dict:
        """Enhanced domain intelligence using live_lookup."""
        if "://" not in url:
            url = "https://" + url
        domain = urlparse(url).netloc.split(":")[0]
        domain = domain[4:] if domain.startswith("www.") else domain

        # Use comprehensive domain intelligence
        intel = domain_intelligence(domain)

        return {
            "domain": domain,
            "domain_age_days": intel["domain_age_days"],
            "ssl_valid": intel["ssl_valid"],
            "ssl_issuer": intel.get("ssl_issuer", ""),
            "ssl_expires": intel.get("ssl_expires", ""),
            "is_ip_address": intel["is_ip_address"],
            "has_suspicious_tld": intel["has_suspicious_tld"],
            "registrar": intel.get("registrar", ""),
            "country": intel.get("country", ""),
        }

    def detect_typosquatting(self, url: str, official_domains: List[str]) -> Dict:
        """Enhanced typosquatting detection with multiple algorithms."""
        if "://" not in url:
            url = "https://" + url
        first = urlparse(url).netloc.split(":")[0]
        first = first[4:] if first.startswith("www.") else first
        first_label = first.split(".")[0]

        best_match = {"is_typosquat": False, "imitating": "", "similarity": 0, "type": ""}

        for official in official_domains:
            official_label = official.split(".")[0]

            # SequenceMatcher similarity
            sim = SequenceMatcher(None, first_label, official_label).ratio()

            # Check for brand + suspicious keyword pattern
            brand_lower = official_label.lower()
            test_lower = first_label.lower()

            for pattern in BRAND_IMPERSONATION_PATTERNS:
                pat = pattern.format(brand=re.escape(brand_lower))
                if re.search(pat, test_lower):
                    return {
                        "is_typosquat": True,
                        "imitating": official,
                        "similarity": round(sim, 2),
                        "type": "brand_keyword_pattern",
                    }

            # High similarity but not exact
            if 0.75 < sim < 1.0:
                if sim > best_match["similarity"]:
                    best_match = {
                        "is_typosquat": True,
                        "imitating": official,
                        "similarity": round(sim, 2),
                        "type": "high_similarity",
                    }

            # Subdomain impersonation (brand.official.fakesite.com)
            if official_label in first_label and first_label != official_label:
                return {
                    "is_typosquat": True,
                    "imitating": official,
                    "similarity": 0.95,
                    "type": "subdomain_impersonation",
                }

        return best_match

    def check_security_apis(self, url: str) -> Dict:
        """Aggregate security API results."""
        domain = self.get_domain_info(url)["domain"]
        results = {
            "safe_browsing": safe_browsing_check(url),
            "virustotal": virustotal_reputation(domain),
            "urlvoid": urlvoid_scan(domain),
            "community_reports": community_scam_reports(domain),
        }
        return results

    def analyze_page_content(self, url: str, product_info: Dict) -> Dict:
        """LLM-based page content analysis for scam indicators."""
        from live_lookup import fetch_page_text
        from gemini_client import analyze_page_llm

        text = fetch_page_text(url)
        if not text:
            return {"error": "Could not fetch page"}

        # Try LLM analysis if Gemini available
        if get_keys().has_gemini():
            try:
                return analyze_page_llm(url, text, product_info)
            except Exception as e:
                print(f"LLM page analysis failed: {e}")

        # Fallback: heuristic content analysis
        return self._heuristic_page_analysis(text, product_info)

    def _heuristic_page_analysis(self, text: str, product_info: Dict) -> Dict:
        """Heuristic analysis when LLM unavailable."""
        text_lower = text.lower()
        brand = (product_info.get("brand") or "").lower()

        signals = {
            "detected_brand": "unknown",
            "detected_product": "",
            "detected_price": "",
            "price_too_low": False,
            "missing_business_info": False,
            "poor_quality_indicators": False,
            "payment_red_flags": False,
            "verdict": "legitimate",
            "reason": "",
        }

        # Brand detection
        if brand and brand in text_lower:
            signals["detected_brand"] = brand

        # Price extraction
        price_matches = re.findall(r'[\$\£\€\₹]\s?\d+(?:[,\.]\d{1,2})?', text)
        if price_matches:
            signals["detected_price"] = price_matches[0]

        # Suspicious indicators
        suspicious_count = 0

        # Missing business info
        business_terms = ["contact", "about us", "privacy policy", "terms", "return", "shipping", "address", "phone"]
        missing = [t for t in business_terms if t not in text_lower]
        if len(missing) > 4:
            signals["missing_business_info"] = True
            suspicious_count += 1

        # Poor quality
        quality_indicators = ["lorem ipsum", "template", "placeholder", "coming soon", "under construction"]
        if any(q in text_lower for q in quality_indicators):
            signals["poor_quality_indicators"] = True
            suspicious_count += 1

        # Payment red flags
        payment_flags = ["western union", "moneygram", "bitcoin", "crypto", "wire transfer", "bank transfer only"]
        if any(p in text_lower for p in payment_flags):
            signals["payment_red_flags"] = True
            suspicious_count += 2

        # Price too low (if we have estimated range)
        est_range = product_info.get("estimated_price_range", "")
        if est_range and signals["detected_price"]:
            suspicion = self.price_suspicion(signals["detected_price"], est_range)
            if suspicion:
                signals["price_too_low"] = True
                suspicious_count += 2

        if suspicious_count >= 3:
            signals["verdict"] = "scam"
        elif suspicious_count >= 1:
            signals["verdict"] = "suspicious"

        signals["reason"] = f"Heuristic analysis: {suspicious_count} suspicious signals"
        return signals

    # ---------- Price Sanity ----------
    @staticmethod
    def _first_number(s: str) -> Optional[float]:
        if not s:
            return None
        m = re.search(r"\d+(?:\.\d{1,2})?", str(s).replace(",", ""))
        return float(m.group()) if m else None

    @staticmethod
    def _numbers(s: str) -> List[float]:
        if not s:
            return []
        return [float(m) for m in re.findall(r"\d+(?:\.\d{1,2})?", str(s).replace(",", ""))]

    def price_suspicion(self, page_price: str, est_range: str) -> Optional[str]:
        p = self._first_number(page_price)
        nums = self._numbers(est_range)
        if p is not None and nums:
            low = min(nums)
            if low > 0 and p < 0.5 * low:
                pct = int((1 - p / low) * 100)
                return f"Price ({page_price}) is ~{pct}% BELOW normal price (~{low:.0f})"
        return None

    # ---------- Decisive Verdict ----------
    def decide(self, url: str, rag_match: Dict, official_domains: List[str],
               page_price: str = None, est_price_range: str = None) -> Dict:
        """
        Multi-signal weighted verdict:
        - Security APIs (Safe Browsing, VirusTotal, URLVoid)
        - Domain intelligence (age, SSL, WHOIS)
        - Typosquatting detection
        - Page content analysis
        - Price sanity
        - RAG registry match
        """
        info = self.get_domain_info(url)
        security = self.check_security_apis(url)
        typo = self.detect_typosquatting(url, official_domains)
        page_analysis = self.analyze_page_content(url, {"brand": "", "estimated_price_range": est_price_range})

        reasons = []
        red_score = 0
        green_score = 0

        # --- RAG Registry Match (Highest Weight) ---
        if rag_match["status"] == "official":
            green_score += 50
            reasons.append(f"✅ {rag_match['reason']}")
            if info["ssl_valid"]:
                green_score += 10
                reasons.append("Valid SSL certificate")
            if info["domain_age_days"] > 365:
                green_score += 10
                reasons.append(f"Domain is {info['domain_age_days']//365}+ years old")

        elif rag_match["status"] == "authorized":
            green_score += 40
            reasons.append(f"✅ {rag_match['reason']}")

        elif rag_match["status"] == "scam_pattern":
            red_score += 30
            reasons.append(f"🚨 {rag_match['reason']}")

        elif rag_match["status"] == "impersonation":
            red_score += 25
            reasons.append(f"🚨 {rag_match['reason']}")

        # --- Security APIs ---
        sb = security["safe_browsing"]
        if sb is True:
            red_score += 40
            reasons.append("🚨 Google Safe Browsing: FLAGGED as phishing/malware")
        elif sb is False:
            green_score += 5
            reasons.append("✅ Google Safe Browsing: Clean")

        vt = security["virustotal"]
        if vt and vt.get("malicious", 0) > 0:
            red_score += 20 + min(vt["malicious"] * 5, 30)
            reasons.append(f"🚨 VirusTotal: {vt['malicious']} engines flag as malicious")

        uv = security["urlvoid"]
        if uv and uv.get("raw", {}).get("detected", 0) > 0:
            red_score += 15
            reasons.append("🚨 URLVoid: Detected by security engines")

        reports = security["community_reports"]
        if reports:
            red_score += min(len(reports) * 5, 25)
            reasons.append(f"⚠️ {len(reports)} community scam reports found")

        # --- Typosquatting ---
        if typo.get("is_typosquat"):
            red_score += 35
            reasons.append(f"🚨 Typosquatting: imitates {typo['imitating']} ({typo['type']})")

        # --- Domain Intelligence ---
        if info["is_ip_address"]:
            red_score += 30
            reasons.append("🚨 Uses IP address instead of domain name")

        age = info["domain_age_days"]
        if age == -1:
            red_score += 10
            reasons.append("⚠️ Domain age could not be verified")
        elif age < 30:
            red_score += 25
            reasons.append(f"🚨 Domain is only {age} days old — scam sites are usually brand new")
        elif age < 90:
            red_score += 15
            reasons.append(f"⚠️ Domain is only {age} days old")
        elif age > 730:
            green_score += 10
            reasons.append(f"✅ Domain is {age//365} years old")

        if not info["ssl_valid"]:
            red_score += 15
            reasons.append("🚨 Invalid or missing SSL certificate (not secure)")
        elif info.get("ssl_issuer") and "Let's Encrypt" not in info["ssl_issuer"]:
            green_score += 5
            reasons.append(f"✅ SSL issued by {info['ssl_issuer']}")

        if info["has_suspicious_tld"]:
            red_score += 10
            tld = url.split(".")[-1]
            reasons.append(f"⚠️ Uses suspicious TLD (.{tld})")

        if info.get("registrar") and any(x in info["registrar"].lower() for x in ["namecheap", "godaddy", "porkbun"]):
            # Common registrars, not necessarily bad
            pass

        # --- Page Content Analysis ---
        if "error" not in page_analysis:
            verdict = page_analysis.get("verdict", "legitimate")
            if verdict == "scam":
                red_score += 25
                reasons.append(f"🚨 Page content analysis: SCAM - {page_analysis.get('reason', '')}")
            elif verdict == "suspicious":
                red_score += 15
                reasons.append(f"⚠️ Page content analysis: SUSPICIOUS - {page_analysis.get('reason', '')}")
            else:
                green_score += 5
                reasons.append("✅ Page content appears legitimate")

            if page_analysis.get("price_too_low"):
                red_score += 15
                reasons.append("🚨 Price significantly below market rate")

            if page_analysis.get("missing_business_info"):
                red_score += 10
                reasons.append("⚠️ Missing standard business information (contact, policy, etc.)")

            if page_analysis.get("payment_red_flags"):
                red_score += 20
                reasons.append("🚨 Suspicious payment methods requested")

        # --- Price Sanity ---
        flag = self.price_suspicion(page_price, est_price_range)
        if flag:
            red_score += 20
            reasons.append(f"🚨 {flag}")

        # --- Final Verdict ---
        net_score = green_score - red_score

        if net_score >= 20:
            label = "GENUINE"
            kind = rag_match["status"] if rag_match["status"] in ("official", "authorized") else "verified"
        elif net_score <= -15:
            label = "FAKE"
            kind = rag_match["status"] if rag_match["status"] in ("scam_pattern", "impersonation") else "detected"
        else:
            label = "UNVERIFIED"
            kind = "unknown"

        return {
            "label": label,
            "kind": kind,
            "net_score": net_score,
            "green_score": green_score,
            "red_score": red_score,
            "reasons": reasons,
            "domain_info": info,
            "security_apis": security,
            "typosquatting": typo,
            "page_analysis": page_analysis,
        }