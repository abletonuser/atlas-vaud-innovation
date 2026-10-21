"""Diagnostic ponctuel : formulaire de la liste ARAMIS, recherche par numéro et stabilité de la pagination selon le tri."""
import re, html, time, requests
L = "https://datenausgabe.aramis.admin.ch/projects"
S = requests.Session(); S.headers["User-Agent"] = "atlas-vaud-innovation/1.0 (diagnostic)"
h = S.get(L, timeout=60).text
print("LONGUEUR", len(h))
form = re.search(r"(?is)<form\b.*?</form>", h)
print("FORMULAIRE", re.sub(r"\s+", " ", form.group(0))[:3000] if form else None)
names = re.findall(r'(?is)<(?:input|select)\b[^>]*\bname="([^"]+)"', h)
print("CHAMPS", names)
for m in sorted(set(re.findall(r'href="([^"]*(?:q%5Bs%5D|q\[s\])[^"]*)"', h)))[:30]: print("TRI", html.unescape(m))
th = re.search(r"(?is)<thead.*?</thead>", h); print("ENTETE", re.sub(r"\s+", " ", th.group(0))[:2000] if th else None)
tr = re.findall(r"(?is)<tr\b.*?</tr>", h); print("LIGNE", re.sub(r"\s+", " ", tr[1])[:1500] if len(tr) > 1 else None)
filt = {}
for name, body in re.findall(r'(?is)<select\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</select>', h):
    for val, lab in re.findall(r'(?is)<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)</option>', body):
        if "INNOSUISSE" in lab and "EVAL" not in lab and val: filt = {html.unescape(name): html.unescape(val)}
print("FILTRE", filt)
def ids(params):
    t = S.get(L, params=params, timeout=60).text
    return re.findall(r"ProjectID=(\d+)", t), t
for n in set(names):
    if "utf8" in n or "commit" in n or n in filt: continue
    r, t = ids({n: "35796.1"}); time.sleep(0.3)
    print("RECHERCHE", n, len(r), r[:5], re.findall(r"\d{5}\.\d\s+[A-Z]+-[A-Z]+", t)[:5])
variants = {
  "simple": lambda p: {"q[s]": "start_date desc", "page": p, **filt},
  "multi_id": lambda p: [("q[s][]", "start_date desc"), ("q[s][]", "id desc"), ("page", p)] + list(filt.items()),
  "multi_num": lambda p: [("q[s][]", "start_date desc"), ("q[s][]", "project_number desc"), ("page", p)] + list(filt.items()),
  "id_seul": lambda p: {"q[s]": "id desc", "page": p, **filt},
}
for name, f in variants.items():
    allids = []
    for p in range(1, 41):
        r, t = ids(f(p)); allids += r; time.sleep(0.3)
        if p == 1: print(name, "page1", r[:8], "dates", re.findall(r"\d{2}\.\d{2}\.\d{4}", t)[:6])
    print("VARIANTE", name, "lignes", len(allids), "uniques", len(set(allids)))
