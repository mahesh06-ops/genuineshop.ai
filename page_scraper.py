import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

def extract_page_info(url: str) -> dict:
    info = {"url": url, "title": "", "description": "", "image": None, "price": None}
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        t = soup.find("meta", property="og:title") or soup.find("title")
        if t:
            info["title"] = (t.get("content") if t.has_attr("content") else t.get_text())[:300].strip()

        d = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if d and d.get("content"):
            info["description"] = d["content"][:1000]

        img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
        if img and img.get("content"):
            info["image"] = img["content"]

        # price extraction (tries standard product meta tags first)
        for attrs in ({"property": "product:price:amount"}, {"itemprop": "price"}):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                info["price"] = tag["content"]; break
        if not info["price"]:
            el = soup.find(class_=lambda c: c and "price" in str(c).lower())
            if el:
                info["price"] = el.get_text(" ", strip=True)[:50]
    except Exception as e:
        info["description"] = f"(Could not load page: {e})"
    return info