import httpx
from bs4 import BeautifulSoup
from backend.config import USER_AGENT

url = "https://www.1mg.com/drugs/actorise-40-injection-227647"
r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20.0)
soup = BeautifulSoup(r.text, "html.parser")
tags = [t for t in soup.find_all(True) if "how to use" in t.get_text().lower()]
innermost = min(tags, key=lambda t: len(t.get_text()))

cur = innermost
for i in range(4):
    print(f"Level {i}: <{cur.name}> class={cur.get('class')}")
    for s in cur.find_next_siblings()[:3]:
        print(f"   Sibling: <{s.name}> class={s.get('class')} text={repr(s.get_text(strip=True)[:80])}")
    cur = cur.parent
