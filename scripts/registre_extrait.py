"""Extrait du registre du commerce (Zefix sur LINDAS), pour attribuer un numéro IDE aux organisations sans numéro
(scale-ups suivies, partenaires Innosuisse et participants UE sans IDE).

Trois sorties dans data/state/registre/ :
  schema.txt        prédicats d'une entreprise connue (contrôle du modèle de données LINDAS)
  registre_vd.csv.gz toutes les entités dont le siège est dans une commune vaudoise (IDE, raison sociale, commune OFS, forme)
  recherche.csv      recherche par nom dans toute la Suisse, pour les motifs de recherche_motifs.txt (un par ligne)

Usage : python scripts/registre_extrait.py [--sans-vd] [--sans-recherche]
"""
import argparse, csv, gzip, json, os, re, time
import requests

ENDPOINTS = ["https://ld.admin.ch/query", "https://lindas.admin.ch/query"]
OUT = "data/state/registre"
PREFIX = """PREFIX schema: <http://schema.org/>
PREFIX admin: <https://schema.ld.admin.ch/>
"""
EXEMPLE = ("CHE330040916", "CHE-330.040.916")   # Distalmotion SA, Epalinges


def sparql(q, timeout=300):
    last = None
    for ep in ENDPOINTS:
        for essai in range(3):
            try:
                r = requests.post(ep, data={"query": q}, headers={"Accept": "application/sparql-results+json",
                                  "User-Agent": "atlas-vaud-innovation/1.0"}, timeout=timeout)
                r.raise_for_status()
                return r.json()["results"]["bindings"]
            except Exception as e:
                last = e
                time.sleep(5 * (essai + 1))
    raise RuntimeError(f"LINDAS ne répond pas : {last}")


def v(b, k):
    return b.get(k, {}).get("value", "")


def uid_norm(s):
    d = re.sub(r"\D", "", s or "")
    return "CHE" + d if len(d) == 9 else ""


def bfs(uri):
    m = re.search(r"(\d+)$", uri or "")
    return m.group(1) if m else ""


def schema():
    q1 = PREFIX + f"""SELECT ?p ?o WHERE {{
  ?id schema:value ?val . VALUES ?val {{ "{EXEMPLE[0]}" "{EXEMPLE[1]}" }}
  ?c schema:identifier ?id . ?c ?p ?o }} LIMIT 200"""
    q2 = PREFIX + f"""SELECT ?p ?o WHERE {{
  ?id schema:value ?val . VALUES ?val {{ "{EXEMPLE[0]}" "{EXEMPLE[1]}" }}
  ?c schema:identifier ?id . ?c schema:identifier ?i . ?i ?p ?o }} LIMIT 200"""
    lignes = ["# entreprise"] + [f"{v(b, 'p')}\t{v(b, 'o')}" for b in sparql(q1)]
    lignes += ["# identifiants"] + [f"{v(b, 'p')}\t{v(b, 'o')}" for b in sparql(q2)]
    with open(f"{OUT}/schema.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")
    print(f"Schéma : {len(lignes)} lignes")


def extrait_vd():
    communes = sorted(json.load(open("data/ref/vd_commune_district.json", encoding="utf-8")), key=int)
    rows, vus = [], set()
    for k in range(0, len(communes), 12):
        lot = communes[k:k + 12]
        vals = " ".join(f"<https://ld.admin.ch/municipality/{c}>" for c in lot)
        off, page = 0, 10000
        while True:
            q = PREFIX + f"""SELECT ?c ?uid ?name ?muni ?form WHERE {{
  VALUES ?muni {{ {vals} }}
  ?c admin:municipality ?muni ; schema:identifier ?id . ?id schema:value ?uid .
  FILTER(STRSTARTS(STR(?uid), "CHE"))
  OPTIONAL {{ ?c schema:legalName ?name }}
  OPTIONAL {{ ?c schema:additionalType ?form }}
}} ORDER BY ?c ?uid LIMIT {page} OFFSET {off}"""
            res = sparql(q)
            for b in res:
                u = uid_norm(v(b, "uid"))
                if not u or (u, v(b, "name")) in vus:
                    continue
                vus.add((u, v(b, "name")))
                rows.append([u, v(b, "name"), bfs(v(b, "muni")), v(b, "form").rsplit("/", 1)[-1], v(b, "c")])
            if len(res) < page:
                break
            off += page
        print(f"  communes {k + len(lot)}/{len(communes)} : {len(rows)} entités")
        time.sleep(1)
    with gzip.open(f"{OUT}/registre_vd.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["UID", "Name", "MunicipalityBFS", "LegalForm", "Uri"])
        w.writerows(sorted(rows))
    print(f"Registre VD : {len(rows)} lignes")


ACC = {"a": "[aàâäá]", "e": "[eéèêë]", "i": "[iîïí]", "o": "[oôöó]", "u": "[uùûüú]", "c": "[cç]", "n": "[nñ]"}


def motif_regex(m):
    m = re.sub(r"[^a-z0-9 ]", "", m.lower())
    corps = "".join(ACC.get(ch, ch) if ch != " " else "[^a-z0-9]*" for ch in m)
    return f"(^|[^a-z0-9]){corps}([^a-z0-9]|$)"     # mot entier (XPath ne connaît pas \\b)


def recherche():
    src = f"{OUT}/recherche_motifs.txt"
    if not os.path.exists(src):
        print("Pas de motifs à chercher"); return
    motifs = [l.strip() for l in open(src, encoding="utf-8") if l.strip() and not l.startswith("#")]
    rows = []
    for k in range(0, len(motifs), 20):
        lot = motifs[k:k + 20]
        rx = "|".join(motif_regex(m) for m in lot)
        q = PREFIX + f"""SELECT ?c ?uid ?name ?muni ?form WHERE {{
  ?c schema:legalName ?name . FILTER(REGEX(STR(?name), "{rx}", "i"))
  ?c schema:identifier ?id . ?id schema:value ?uid . FILTER(STRSTARTS(STR(?uid), "CHE"))
  OPTIONAL {{ ?c admin:municipality ?muni }}
  OPTIONAL {{ ?c schema:additionalType ?form }}
}} LIMIT 6000"""
        try:
            res = sparql(q, timeout=600)
        except Exception as e:
            print(f"  lot {k}: échec {e}"); continue
        for b in res:
            u = uid_norm(v(b, "uid"))
            if u:
                rows.append([u, v(b, "name"), bfs(v(b, "muni")), v(b, "form").rsplit("/", 1)[-1]])
        print(f"  motifs {k + len(lot)}/{len(motifs)} : {len(rows)} résultats")
        time.sleep(1)
    with open(f"{OUT}/recherche.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["UID", "Name", "MunicipalityBFS", "LegalForm"])
        w.writerows(sorted(set(map(tuple, rows))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sans-vd", action="store_true"); ap.add_argument("--sans-recherche", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for nom, f in [("schéma", schema), ("registre VD", None if a.sans_vd else extrait_vd),
                   ("recherche", None if a.sans_recherche else recherche)]:
        if f is None:
            continue
        try:
            f()
        except Exception as e:
            print(f"Étape {nom} en échec : {e}")


if __name__ == "__main__":
    main()
