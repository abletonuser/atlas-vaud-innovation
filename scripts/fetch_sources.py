"""Télécharge les sources publiques de l'atlas dans data/raw/ (non versionné).

  - CORDIS H2020 et Horizon Europe : archives CSV des projets (organization.csv, project.csv, euroSciVoc.csv)
  - ARAMIS : export complet des projets de l'administration fédérale (CSV)
  - Eurostat : population au 1er janvier par pays et région NUTS 3 (met à jour data/ref/population.json)

Les liens CORDIS sont retrouvés dans le catalogue data.europa.eu ; à défaut, les adresses habituelles de CORDIS servent.
Usage : python scripts/fetch_sources.py [dossier du dépôt]
"""
import io, json, os, sys, time, zipfile
import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
RAW = os.path.join(BASE, "data", "raw")
UA = {"User-Agent": "atlas-vaud-innovation/1.0 (mise a jour mensuelle, donnees publiques)"}
CORDIS = {
    "horizon": {"dataset": "cordis-eu-research-projects-under-horizon-europe-2021-2027", "title": "HORIZON Projects",
                "fallback": ["https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"]},
    "h2020": {"dataset": "cordisH2020projects", "title": "H2020 Projects",
              "fallback": ["https://cordis.europa.eu/data/cordis-h2020projects-csv.zip"]},
}
ARAMIS_CSV = "https://datenausgabe.aramis.admin.ch/full_export.csv"
WANTED = {"organization.csv", "project.csv", "euroSciVoc.csv"}


def get(url, **kw):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=600, **kw)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"  essai {attempt + 1} échoué pour {url} : {e}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"téléchargement impossible : {url}")


def cordis_urls(key):
    """Liens de téléchargement CSV d'un jeu CORDIS, lus dans le catalogue data.europa.eu."""
    c = CORDIS[key]
    urls = []
    try:
        meta = get(f"https://data.europa.eu/api/hub/search/datasets/{c['dataset']}").json()
        for d in meta.get("result", meta).get("distributions", []):
            title = json.dumps(d.get("title", ""))
            fmt = json.dumps(d.get("format", "")).upper()
            if c["title"].lower() in title.lower() and "CSV" in fmt:
                for k in ("download_url", "access_url"):
                    v = d.get(k)
                    urls += v if isinstance(v, list) else [v] if v else []
    except Exception as e:
        print(f"  catalogue data.europa.eu indisponible ({e}) : adresses CORDIS habituelles")
    return [u for u in urls if u] + c["fallback"]


def fetch_cordis(key):
    out = os.path.join(RAW, key)
    os.makedirs(out, exist_ok=True)
    for url in cordis_urls(key):
        try:
            r = get(url)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            names = {os.path.basename(n): n for n in z.namelist()}
            if not WANTED & set(names):
                continue
            for w in WANTED & set(names):
                with open(os.path.join(out, w), "wb") as f:
                    f.write(z.read(names[w]))
            print(f"CORDIS {key} : {sorted(WANTED & set(names))} depuis {url}")
            return
        except (zipfile.BadZipFile, RuntimeError) as e:
            print(f"  {url} : {e}")
    raise SystemExit(f"CORDIS {key} : aucune archive CSV valide trouvée")


def fetch_aramis():
    r = get(ARAMIS_CSV)
    with open(os.path.join(RAW, "aramis_full_export.csv"), "wb") as f:
        f.write(r.content)
    print(f"ARAMIS : {len(r.content) / 1e6:.1f} Mo")


def fetch_population():
    """Population au 1er janvier (total) ; garde le fichier existant si l'API ne répond pas."""
    path = os.path.join(BASE, "data", "ref", "population.json")
    url = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_r_pjanaggr3"
           "?format=JSON&lang=fr&sex=T&age=TOTAL&unit=NR&sinceTimePeriod=2019")
    try:
        js = get(url).json()
        geo = js["dimension"]["geo"]["category"]["index"]
        tim = js["dimension"]["time"]["category"]["index"]
        size = js["size"]; ids = js["id"]
        gi, ti = ids.index("geo"), ids.index("time")
        stride = [1] * len(size)
        for k in range(len(size) - 2, -1, -1):
            stride[k] = stride[k + 1] * size[k + 1]
        vals = {}
        for g, gpos in geo.items():
            if not (len(g) == 2 or g.startswith("CH")):
                continue
            for t, tpos in sorted(tim.items()):
                v = js["value"].get(str(gpos * stride[gi] + tpos * stride[ti]))
                if v is not None:
                    vals[g] = [int(t), round(float(v))]
        if len(vals) > 50:
            json.dump({"source": "Eurostat demo_r_pjanaggr3, population au 1er janvier, total", "values": vals},
                      open(path, "w"), ensure_ascii=False, indent=0)
            print(f"Eurostat : {len(vals)} territoires")
            return
        print("Eurostat : réponse incomplète, fichier existant conservé")
    except Exception as e:
        print(f"Eurostat indisponible ({e}) : fichier existant conservé")


if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    fetch_cordis("horizon")
    fetch_cordis("h2020")
    fetch_aramis()
    fetch_population()
