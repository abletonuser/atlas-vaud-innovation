"""Diagnostic ponctuel : formulaire de la liste ARAMIS et stabilité de la pagination selon le tri."""
import re, html, time, requests, json
L = "https://datenausgabe.aramis.admin.ch/projects"
S = requests.Session(); S.headers["User-Agent"] = "atlas-vaud-innovation/1.0 (diagnostic)"
h = S.get(L, timeout=60).text
print("LONGUEUR", len(h))
for m in re.findall(r'(?is)<(input|select)\b[^>]*\bname="([^"]+)"', h): print("CHAMP", m)
for m in sorted(set(re.findall(r'href="([^"]*q%5Bs%5D[^"]*|[^"]*q\[s\][^"]*)"', h)))[:30]: print("TRI", html.unescape(m))
filt = {}
for name, body in re.findall(r'(?is)<select\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</select>', h):
    for val, lab in re.findall(r'(?is)<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)</option>', body):
        if "INNOSUISSE" in lab and "EVAL" not in lab and val: filt = {html.unescape(name): html.unescape(val)}
print("FILTRE", filt)
th = re.search(r"(?is)<thead.*?</thead>", h); print("ENTETE", re.sub(r"\s+", " ", th.group(0))[:1500] if th else None)
def ids(params):
    t = S.get(L, params=params, timeout=60).text
    return re.findall(r"ProjectID=(\d+)", t), t
variants = {
  "simple": lambda p: {"q[s]": "start_date desc", "page": p, **filt},
  "multi_id": lambda p: [("q[s][]", "start_date desc"), ("q[s][]", "id desc"), ("page", p)] + list(filt.items()),
  "multi_num": lambda p: [("q[s][]", "start_date desc"), ("q[s][]", "project_number desc"), ("page", p)] + list(filt.items()),
}
for name, f in variants.items():
    allids, n = [], 0
    for p in range(1, 41):
        r, t = ids(f(p)); allids += r; n += 1; time.sleep(0.3)
        if p == 1: print(name, "page1", r[:6])
    print("VARIANTE", name, "lignes", len(allids), "uniques", len(set(allids)))
