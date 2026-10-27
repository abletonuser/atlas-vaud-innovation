"""Siège des entreprises (commune, NPA, localité) à partir de leur numéro IDE, dans les données ouvertes du registre
du commerce (Zefix sur LINDAS). Incrémental : seuls les numéros absents de data/state/ide_sieges.csv sont demandés.
Usage : python scripts/ide_sieges.py [--batch 150] [--test]
"""
import argparse, csv, os, re, time
import requests

ENDPOINTS = ["https://ld.admin.ch/query", "https://lindas.admin.ch/query"]
FIELDS = ["UID", "Name", "MunicipalityBFS", "Municipality", "PostCode", "Town", "MunicipalityUri"]
PREFIX = """PREFIX schema: <http://schema.org/>
PREFIX admin: <https://schema.ld.admin.ch/>
PREFIX locn: <http://www.w3.org/ns/locn#>
"""


def sparql(q):
    last = None
    for ep in ENDPOINTS:
        try:
            r = requests.post(ep, data={"query": q}, headers={"Accept": "application/sparql-results+json",
                              "User-Agent": "atlas-vaud-innovation/1.0"}, timeout=120)
            r.raise_for_status()
            return r.json()["results"]["bindings"]
        except Exception as e:
            last = e
    raise RuntimeError(f"LINDAS ne répond pas : {last}")


def fmt(u):
    return f"CHE-{u[3:6]}.{u[6:9]}.{u[9:12]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--participants", default="data/state/innosuisse_participants.csv")
    ap.add_argument("--out", default="data/state/ide_sieges.csv")
    ap.add_argument("--batch", type=int, default=150); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    with open(a.participants, encoding="utf-8-sig") as f:
        uids = set()
        for r in csv.DictReader(f):
            if re.fullmatch(r"CHE\d{9}", r.get("UID") or ""):
                uids.add(r["UID"])
            m = re.search(r"CHE-?(\d{3})\.?(\d{3})\.?(\d{3})", r.get("Company") or "")   # numéro collé au nom
            if m:
                uids.add("CHE" + "".join(m.groups()))
    corr = "data/ref/ide_correspondances.csv"       # IDE retrouvés par la raison sociale (scripts/referentiel_ide.py)
    if os.path.exists(corr):
        with open(corr, encoding="utf-8") as f:
            uids |= {r["uid"] for r in csv.DictReader(f) if re.fullmatch(r"CHE\d{9}", r.get("uid") or "")}
    uids = sorted(uids)
    known = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8-sig") as f:
            known = {r["UID"] for r in csv.DictReader(f)}
    todo = [u for u in uids if u not in known][: 5 if a.test else None]
    print(f"Numéros IDE : {len(uids)} ; déjà connus : {len(known)} ; à chercher : {len(todo)}")
    rows = []
    for k in range(0, len(todo), a.batch):
        chunk = todo[k:k + a.batch]
        vals = " ".join(f'"{u}" "{fmt(u)}"' for u in chunk)
        q = PREFIX + f"""SELECT ?uid ?name ?muni ?muniName ?zip ?town ?locality WHERE {{
  VALUES ?uid {{ {vals} }}
  ?id schema:value ?uid . ?company schema:identifier ?id .
  OPTIONAL {{ ?company schema:legalName ?name }}
  OPTIONAL {{ ?company admin:municipality ?muni . OPTIONAL {{ ?muni schema:name ?muniName }} }}
  OPTIONAL {{ ?company schema:address ?a .
    OPTIONAL {{ ?a locn:postCode ?zip }} OPTIONAL {{ ?a schema:postalCode ?zip }}
    OPTIONAL {{ ?a locn:postName ?town }} OPTIONAL {{ ?a schema:addressLocality ?locality }} }}
}}"""
        seen = set()
        for b in sparql(q):
            v = lambda key: b.get(key, {}).get("value", "")
            u = "CHE" + re.sub(r"\D", "", v("uid"))
            if u in seen:
                continue
            seen.add(u)
            muni = v("muni")
            rows.append({"UID": u, "Name": v("name"), "MunicipalityBFS": (re.search(r"(\d+)$", muni) or [None, ""])[1],
                         "Municipality": v("muniName"), "PostCode": v("zip"), "Town": v("town") or v("locality"), "MunicipalityUri": muni})
        print(f"  {min(k + a.batch, len(todo))}/{len(todo)} : {len(rows)} retrouvés")
        time.sleep(1)
    if a.test:
        for r in rows:
            print(f"  {r['UID']} {r['Name']} -> {r['PostCode']} {r['Town']} (OFS {r['MunicipalityBFS']})")
        return
    new = not os.path.exists(a.out)
    with open(a.out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"Terminé : {len(rows)} sièges ajoutés à {a.out}")


if __name__ == "__main__":
    main()
