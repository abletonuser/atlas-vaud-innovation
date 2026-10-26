"""Construit le jeu de données de la carte des projets d'innovation financés (Vaud).

Entrées (cache pickle) : CORDIS Horizon Europe (organization, project, euroSciVoc), export ARAMIS.
Références : NPA GeoNames (paquet npm swiss-zipcodes), communes et cantons swiss-maps 2026.
Sortie : build/data.json (consommé par la page) + build/qa.txt (contrôles).
Usage : python3 build_data.py <dossier du dépôt>
"""
import json, re, sys, unicodedata
import shapefile
from collections import Counter
import pandas as pd
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

BASE = sys.argv[1]
C, B = f"{BASE}/data/cache", f"{BASE}/build"
qa = []
def log(*a):
    s = " ".join(str(x) for x in a); qa.append(s); print(s)

# ---------- Référentiels géographiques ----------
muni = json.load(open(f"{B}/ch_municipalities.geojson"))
vd_dist = {int(k): v for k, v in json.load(open(f"{BASE}/data/ref/vd_commune_district.json")).items()}
zips = json.load(open(f"{BASE}/data/ref/ch_zip_geonames.json"))
names = {int(r["community_code"]): r["community"] for r in zips if r["community_code"]}
names.update({5656: "Hautemorges", 5892: "Blonay - Saint-Légier"})   # fusions postérieures à la référence NPA

vd_geoms, vd_ids = [], []
for f in muni["features"]:
    if int(f["id"]) in vd_dist:
        vd_geoms.append(shape(f["geometry"])); vd_ids.append(int(f["id"]))
tree = STRtree(vd_geoms)
def commune_of(lat, lon, tol_km=1.5):
    """Commune vaudoise contenant le point ; à défaut la plus proche à moins de tol_km (points sur la rive)."""
    p = Point(lon, lat)
    for i in tree.query(p):
        if vd_geoms[i].contains(p): return vd_ids[i]
    i = tree.nearest(p)
    return vd_ids[i] if vd_geoms[i].distance(p) * 111 <= tol_km else None

def norm(s): return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()
zip_ref, place_ref = {}, {}
for r in zips:
    zip_ref.setdefault(r["zipcode"], r); place_ref.setdefault(norm(r["place"]), r)

def locate(geoloc=None, npa=None, city=None):
    """Position et commune : géolocalisation fournie, sinon centroïde du NPA, sinon nom de localité."""
    cands = []
    if isinstance(geoloc, str) and "," in geoloc:
        try: cands.append(tuple(float(x) for x in geoloc.split(",")))
        except ValueError: pass
    z = zip_ref.get(str(npa).strip()[:4]) if npa else None
    if z: cands.append((float(z["latitude"]), float(z["longitude"])))
    pl = place_ref.get(norm(city)) if city else None
    if pl: cands.append((float(pl["latitude"]), float(pl["longitude"])))
    for ll in cands:
        bfs = commune_of(*ll)
        if bfs: return ll, bfs
    return (cands[0] if cands else None), None

CANTON_ID = {"ZH":1,"BE":2,"LU":3,"UR":4,"SZ":5,"OW":6,"NW":7,"GL":8,"ZG":9,"FR":10,"SO":11,"BS":12,"BL":13,
             "SH":14,"AR":15,"AI":16,"SG":17,"GR":18,"AG":19,"TG":20,"TI":21,"VD":22,"VS":23,"NE":24,"GE":25,"JU":26}
NUTS3_CANTON = {"CH011":"VD","CH012":"VS","CH013":"GE","CH021":"BE","CH022":"FR","CH023":"SO","CH024":"NE",
                "CH025":"JU","CH031":"BS","CH032":"BL","CH033":"AG","CH040":"ZH","CH051":"GL","CH052":"SH",
                "CH053":"AR","CH054":"AI","CH055":"SG","CH056":"GR","CH057":"TG","CH061":"LU","CH062":"UR",
                "CH063":"SZ","CH064":"OW","CH065":"NW","CH066":"ZG","CH070":"TI"}

# ---------- Organisations : noms canoniques et catégories ----------
CANON = [(r"\bEPFL\b|POLYTECHNIQUE F[ÉE]D[ÉE]RALE DE LAUSANNE", "EPFL"),
         (r"UNIVERSIT[ÉE] DE LAUSANNE|\bUNIL\b", "Université de Lausanne"),
         (r"\bCHUV\b|HOSPITALIER UNIVERSITAIRE VAUDOIS", "CHUV"),
         (r"\bHEIG\b|ING[ÉE]NIERIE ET DE GESTION", "HEIG-VD"),
         (r"UNISANT|\bPMU\b|POLICLINIQUE M[ÉE]DICALE", "Unisanté"),
         (r"\bEHL\b|[ÉE]COLE H[ÔO]TELI[ÈE]RE", "EHL"), (r"\bECAL\b", "ECAL"), (r"\bHESAV\b", "HESAV"),
         (r"LA SOURCE", "HEdS La Source"), (r"\bHETSL\b|\bEESP\b|\bHETS\b", "HETSL"), (r"\bIMD\b", "IMD"),
         (r"CHANGINS", "Changins"), (r"\bHEMU\b", "HEMU"), (r"AGROSCOPE", "Agroscope"),
         (r"SWISS INSTITUTE OF BIO|\bSIB\b", "SIB Institut suisse de bioinformatique")]
def canon(o):
    if not isinstance(o, str): return None
    for pat, name in CANON:
        if re.search(pat, o, re.I): return name
    return o.strip()
HE = "Haute école"; HS = "Hôpital et santé"; RI = "Institut de recherche"; EN = "Entreprise"; AU = "Autre"
CAT_BY_CANON = {n: HE for n in ["EPFL", "Université de Lausanne", "HEIG-VD", "EHL", "ECAL", "HESAV", "HEdS La Source",
                                "HETSL", "IMD", "Changins", "HEMU"]}
CAT_BY_CANON.update({"CHUV": HS, "Unisanté": HS, "Agroscope": RI, "SIB Institut suisse de bioinformatique": RI})
VD_BY_NAME = set(CAT_BY_CANON) - {"Agroscope", "SIB Institut suisse de bioinformatique"}
HQ_NPA = {"EPFL": "1015", "Université de Lausanne": "1015", "CHUV": "1011", "HEIG-VD": "1401", "Unisanté": "1011",
          "EHL": "1000", "ECAL": "1020", "HESAV": "1011", "HEdS La Source": "1004", "HETSL": "1010", "IMD": "1001",
          "Changins": "1260", "HEMU": "1003"}
# L'adresse postale de l'EPFL (1015 Lausanne) désigne un campus situé sur la commune d'Ecublens.
POS_OVERRIDE = {"EPFL": (46.5191, 6.5668)}
COMPANY = re.compile(r"\b(SA|AG|GmbH|GMBH|Sàrl|SÀRL|Sarl|SARL|Sagl|SAGL|Ltd|LTD|Inc|INC)\b")

# ---------- CORDIS Horizon Europe ----------
org = pd.read_pickle(f"{C}/organization.pkl")
prj = pd.read_pickle(f"{C}/project.pkl")
esv = pd.read_pickle(f"{C}/euroSciVoc.pkl")
# H2020 (2014-2020) : mêmes structures, lues par parse_h2020.py ; on empile les deux programmes-cadres.
org_h = pd.read_pickle(f"{C}/h2020_organization.pkl"); prj_h = pd.read_pickle(f"{C}/h2020_project.pkl")
org = pd.concat([org.assign(fp="Horizon Europe"), org_h.assign(fp="H2020")], ignore_index=True)
prj = pd.concat([prj.assign(fp="Horizon Europe"), prj_h.assign(fp="H2020")], ignore_index=True)
assert not prj["id"].duplicated().any(), "identifiant de projet présent dans les deux programmes"
org["ec"] = pd.to_numeric(org["ecContribution"], errors="coerce").fillna(0)
d = prj["startDate"].where(prj["startDate"].str.match(r"^\d{4}-", na=False), prj["ecSignatureDate"])
prj["year"] = pd.to_numeric(d.str[:4], errors="coerce")
log("CORDIS : projets sans année exploitable", int(prj["year"].isna().sum()), "sur", len(prj))
prj = prj.dropna(subset=["year"]).copy(); prj["year"] = prj["year"].astype(int)
log("CORDIS : participations par programme", dict(org["fp"].value_counts()))
def family(fs):
    fs = fs or ""
    for k in ["ERC", "MSCA"]:
        if k in fs: return k
    if "EIC" in fs or fs.startswith("SME-") or "SMEInst" in fs or "FTI" in fs: return "EIC et instrument PME"
    return "Euratom" if fs.upper().startswith("EURATOM") or fs.startswith("NFRP") else "Collaboratif"
prj["fam"] = prj["fundingScheme"].map(family)
DOM_FR = {"natural sciences": "Sciences naturelles", "engineering and technology": "Ingénierie et technologie",
          "medical and health sciences": "Médecine et santé", "social sciences": "Sciences sociales",
          "humanities": "Sciences humaines", "agricultural sciences": "Sciences agricoles"}
esv["top"] = esv["euroSciVocPath"].str.split("/").str[0].map(DOM_FR)
dom_by_prj = esv.dropna(subset=["top"]).groupby("projectID")["top"].agg(lambda s: sorted(set(s)))

ch = org[org["country"] == "CH"].copy()
ch["canton"] = ch["nutsCode"].map(NUTS3_CANTON)
log("CORDIS : participations suisses", len(ch), "| canton identifié", int(ch["canton"].notna().sum()))
vd = ch[ch["canton"] == "VD"].copy()
log("CORDIS : participations vaudoises", len(vd), "| organisations", vd["organisationID"].nunique(),
    "| projets", vd["projectID"].nunique())
TYPE_EU = {"PRC": EN, "HES": HE, "REC": RI, "PUB": AU, "OTH": AU}

# HES-SO : une seule entité juridique, siège à Delémont (JU), pour toutes ses écoles (HEIG-VD, ECAL, HESAV, HETSL, La Source,
# Changins côté vaudois). CORDIS ne précise pas l'école : ces participations sont comptées au Jura, et signalées sur la page.
hs = ch[ch["name"].str.contains(r"SPECIALISEE DE SUISSE OCCIDENTALE|\bHES-SO\b", case=False, na=False, regex=True)].merge(
    prj[["id", "year"]], left_on="projectID", right_on="id")
hesso = [[0 if f == "H2020" else 1, int(y), int(len(g)), round(float(g["ec"].sum()), 2), int((g["role"] == "coordinator").sum())]
         for (f, y), g in hs.groupby(["fp", "year"])]
log("CORDIS : participations HES-SO (siège Delémont)", len(hs), "| EUR", round(float(hs["ec"].sum()), 2))
known_pids = set(prj["id"])
orgs, parts = {}, []
for _, r in vd.iterrows():
    c = canon(r["name"])
    oid = "E" + (re.sub(r"\W+", "_", c) if c in CAT_BY_CANON else str(r["organisationID"]))   # fusionne les doublons d'une même institution
    if oid not in orgs:
        if c in POS_OVERRIDE:
            ll = POS_OVERRIDE[c]; bfs = commune_of(*ll)
        else:
            ll, bfs = locate(r["geolocation"], r["postCode"], r["city"])
        orgs[oid] = {"id": oid, "name": c if c in CAT_BY_CANON else r["name"],
                     "type": CAT_BY_CANON.get(c, TYPE_EU.get(r["activityType"], AU)),
                     "sme": r["SME"] == "true", "bfs": bfs,
                     "lat": round(ll[0], 5) if ll else None, "lon": round(ll[1], 5) if ll else None, "src": "EU"}
    if r["projectID"] in known_pids:
        parts.append({"o": oid, "p": "E" + str(r["projectID"]), "role": r["role"], "ec": round(float(r["ec"]), 2)})
log("CORDIS : organisations sans commune vaudoise", [o["name"] for o in orgs.values() if o["bfs"] is None])
log("CORDIS : catégories", dict(Counter(o["type"] for o in orgs.values())))

vd_pids = set(vd["projectID"])
eu_projects = {"E" + str(p["id"]): {"acr": p["acronym"], "t": p["title"], "y": int(p["year"]), "fam": p["fam"], "fp": p["fp"],
                                    "dom": dom_by_prj.get(p["id"], []),
                                    "url": f"https://cordis.europa.eu/project/id/{p['id']}"}
               for _, p in prj[prj["id"].isin(vd_pids)].iterrows()}
others = org[org["projectID"].isin(vd_pids)].drop_duplicates(["projectID", "organisationID"])
others = others[~others["organisationID"].isin(vd["organisationID"])]
partner_countries = Counter(others["country"].dropna())
log("CORDIS : pays partenaires", len(partner_countries), "| top", partner_countries.most_common(6))
def bench(g):
    return pd.Series({"n": len(g), "funded": int((g["ec"] > 0).sum()), "ec": float(g["ec"].sum()),
                      "coord": int((g["role"] == "coordinator").sum()), "assoc": int((g["role"] == "associatedPartner").sum()),
                      "prc": int((g["activityType"] == "PRC").sum()), "sme": int((g["SME"] == "true").sum()),
                      "orgs": int(g["organisationID"].nunique()), "projects": int(g["projectID"].nunique())})
cant_eu = ch.dropna(subset=["canton"]).groupby("canton").apply(bench, include_groups=False)
ctry = org.dropna(subset=["country"]).groupby("country").apply(bench, include_groups=False)
log("CORDIS : pays participants", len(ctry), "| rang de la Suisse (participations)",
    int((ctry["n"] > ctry.loc["CH", "n"]).sum()) + 1)
vdy = vd.merge(prj[["id", "year"]], left_on="projectID", right_on="id")
eu_years = {int(y): {"n": int(len(g)), "funded": int((g["ec"] > 0).sum()), "ec": round(float(g["ec"].sum()), 2)}
            for y, g in vdy.groupby("year")}

# ---------- Comparaisons : agrégats par pays et canton, année et type ; population Eurostat ----------
TYPE_SIMPLE = {"PRC": EN, "HES": HE, "REC": RI, "PUB": AU, "OTH": AU}
TYPES_ORDER = [EN, HE, HS, RI, AU]
org2 = org.merge(prj[["id", "year"]], left_on="projectID", right_on="id", how="inner")
org2["fpi"] = (org2["fp"] == "Horizon Europe").astype(int)            # 0 = H2020, 1 = Horizon Europe
org2["t"] = org2["activityType"].map(TYPE_SIMPLE).fillna(AU).map(TYPES_ORDER.index)
org2["cty"] = org2["country"].replace({"EL": "GR", "UK": "GB"})
org2["cant"] = org2["nutsCode"].map(NUTS3_CANTON).map(CANTON_ID)
def bench_rows(df, key):
    g = df.dropna(subset=[key, "year"]).groupby([key, "fpi", "year", "t"]).agg(
        n=("projectID", "size"), coord=("role", lambda s: int((s == "coordinator").sum())),
        funded=("ec", lambda s: int((s > 0).sum())), ec=("ec", "sum"), sme=("SME", lambda s: int((s == "true").sum())))
    return [[k if isinstance(k, str) else int(k), int(f), int(y), int(t), int(r.n), int(r.coord), int(r.funded), round(float(r.ec)), int(r.sme)]
            for (k, f, y, t), r in g.iterrows()]
bench = {"country": bench_rows(org2, "cty"), "canton": bench_rows(org2[org2["cty"] == "CH"], "cant")}
# Projets distincts par territoire : un projet compte une fois, quel que soit le nombre de ses participants du territoire.
# Le masque note les types d'organisation présents (bit t), pour respecter le filtre « types » de la page sans double compte.
def proj_rows(df, key):
    g = df.dropna(subset=[key, "year"]).groupby([key, "projectID"]).agg(fpi=("fpi", "first"), year=("year", "first"),
                                                                       mask=("t", lambda s: int(sum(1 << t for t in set(s)))))
    c = g.groupby([key, "fpi", "year", "mask"]).size()
    return [[k if isinstance(k, str) else int(k), int(f), int(y), int(m), int(n)] for (k, f, y, m), n in c.items()]
bench["country_proj"] = proj_rows(org2, "cty"); bench["canton_proj"] = proj_rows(org2[org2["cty"] == "CH"], "cant")
log("Comparaisons : lignes projets pays", len(bench["country_proj"]), "| cantons", len(bench["canton_proj"]))
oth = others.merge(prj[["id", "year"]], left_on="projectID", right_on="id", how="inner")
oth["fpi"] = (oth["fp"] == "Horizon Europe").astype(int)
oth["cty"] = oth["country"].replace({"EL": "GR", "UK": "GB"})
partners_by_year = [[k, int(f), int(y), int(n)] for (k, f, y), n in oth.dropna(subset=["cty"]).groupby(["cty", "fpi", "year"]).size().items()]
log("Comparaisons : lignes pays", len(bench["country"]), "| lignes cantons", len(bench["canton"]))

# Population au 1er janvier (Eurostat demo_r_pjanaggr3), tenue à jour par fetch_sources.py
pop_raw = {k: (int(v[0]), float(v[1])) for k, v in json.load(open(f"{BASE}/data/ref/population.json"))["values"].items()}
pop = {"country": {("GR" if k == "EL" else "GB" if k == "UK" else k): round(v) for k, (y, v) in pop_raw.items() if len(k) == 2},
       "canton": {CANTON_ID[c]: round(pop_raw[n3][1]) for n3, c in NUTS3_CANTON.items() if n3 in pop_raw},
       "years": dict(Counter(y for k, (y, v) in pop_raw.items() if len(k) == 2 or k.startswith("CH0")))}
log("Population : pays", len(pop["country"]), "| cantons", len(pop["canton"]), "| années", pop["years"],
    "| CH", pop["country"].get("CH"), "| VD", pop["canton"].get(22))

# ---------- ARAMIS / Innosuisse ----------
ar = pd.read_pickle(f"{C}/aramis.pkl")
ino = ar[ar["Forschungsstelle"] == "INNOSUISSE"].copy()
ino["start"] = pd.to_datetime(ino["Projektstart"], format="%Y-%m-%d", errors="coerce")
ino = ino[ino["start"] >= "2018-01-01"].copy()
ino["chf"] = pd.to_numeric(ino["Gesamtkosten bewilligt"], errors="coerce").fillna(0)
ino["inst"] = ino["Projektnummer"].str.extract(r"\s([A-Z]+)-")[0]
INSTR = {"IP": "Projet d'innovation", "INNO": "Chèque d'innovation et petits projets", "INT": "Projet international"}
ino["instr"] = ino["inst"].map(INSTR).fillna("Autre (ancien régime CTI)")
BER = {"70": "Ingénierie", "23": "Ingénierie", "22": "Ingénierie", "60": "Sciences de la vie", "20": "Sciences de la vie",
       "50": "TIC", "90": "Sciences sociales et management", "80": "Énergie et environnement", "21": "Enabling sciences"}
ino["dom"] = ino["Bereich"].str.extract(r"^(\d+)")[0].map(BER).fillna("Autre")

TITLES = {"DOKTOR", "PROFESSOR", "PROF", "DR", "PROF DR", "PROFESSOR DOKTOR", "PD", "MONSIEUR", "MADAME", "HERR",
          "FRAU", "PROFESSEUR", "DOCTEUR", "PROF. DR."}
ORGKW = re.compile(r"\b(EPFL|ETH|ETHZ|HES|HEIG|ZHAW|FHNW|BFH|HSLU|OST|SUPSI|EMPA|EAWAG|PSI|WSL|CSEM|IDIAP|UNIL|IMD|EHL|"
                   r"ECAL|HESAV|HEMU|HETSL|EESP|HETS|CHUV|PMU|SIB|SA|AG|GMBH|SÀRL|SARL|SAGL|LTD|INC)\b|UNIV|ECOLE|"
                   r"ÉCOLE|HAUTE|SCHOOL|HOCHSCHULE|INSTITUT|AGROSCOPE|SPITAL|H[ÔO]PITAL|CENTER|CENTRE|FOUNDATION|"
                   r"STIFTUNG|FONDATION|CLINIQUE|KLINIK|LA SOURCE|CHANGINS|UNISANT|POLICLINIQUE", re.I)
ZIPLINE = re.compile(r"^CH-?\s?(\d{4})\s+(.+)$")
def parse_contact(k):
    """Renvoie (organisation, NPA, localité) ; la ligne du nom de personne est écartée (règle 8)."""
    if not isinstance(k, str): return None, None, None
    lines = [l.strip() for l in k.split("\n") if l.strip() and "@" not in l]
    npa = city = None; cut = len(lines)
    for i, l in enumerate(lines):
        m = ZIPLINE.match(l)
        if m: npa, city, cut = m.group(1), m.group(2), i
    body = [l for l in lines[:cut] if l.upper().strip(". ") not in TITLES]
    if not body: return None, npa, city
    j = 0 if (ORGKW.search(body[0]) or len(body) == 1) else 1
    o = body[j]
    if j + 1 < len(body) and body[j + 1][:1].islower():       # raison sociale tronquée à 35 caractères
        o += body[j + 1]
    if not ORGKW.search(o) and re.fullmatch(r"[A-ZÀ-Ý][\w\-']+( [A-ZÀ-Ý][\w\-']+){1,2}", o):
        o = None                                               # garde-fou : ressemble à un nom de personne
    return o, npa, city
parsed = ino["Kontaktperson"].map(parse_contact)
ino["org"], ino["npa"], ino["city"] = parsed.str[0], parsed.str[1], parsed.str[2]
ino["canton"] = ino["npa"].map(lambda z: zip_ref[z]["state_code"] if z in zip_ref else None)
ino["canon"] = ino["org"].map(canon)
ino["is_company"] = ino["org"].fillna("").map(lambda s: bool(COMPANY.search(s)))
ino["vd_by_name"] = ino["npa"].isna() & ino["canon"].isin(VD_BY_NAME)
log("ARAMIS : projets Innosuisse 2018+", len(ino), "| NPA lu", int(ino["npa"].notna().sum()),
    "| organisation lue", int(ino["org"].notna().sum()))
ivd = ino[(ino["canton"] == "VD") | ino["vd_by_name"]].copy()
log("ARAMIS : projets avec contact vaudois", len(ivd), "| par adresse", int((ivd["canton"] == "VD").sum()),
    "| par nom d'institution (siège)", int(ivd["vd_by_name"].sum()), "| CHF", round(ivd["chf"].sum(), 2))
# Entreprises de contact sans adresse : rapprochement exact (nom normalisé) avec les entreprises vaudoises de CORDIS.
def nkey(x):
    x = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().upper()
    x = re.sub(r"\b(SA|AG|SARL|S A R L|GMBH|SAGL|LTD|INC|EN LIQUIDATION|IN LIQUIDATION)\b", "", x)
    return re.sub(r"[^A-Z0-9]+", " ", x).strip()
co_index = {}
for _, r in vd[vd["activityType"] == "PRC"].iterrows():
    k = nkey(r["name"])
    if len(k) >= 4: co_index.setdefault(k, "E" + str(r["organisationID"]))
ino["k"] = ino["org"].map(nkey)
by_name = ino[ino["npa"].isna() & ino["is_company"] & ino["k"].isin(co_index)].copy()
log("ARAMIS : entreprises vaudoises retrouvées par leur nom dans CORDIS", by_name["org"].nunique(), "| projets", len(by_name),
    "| CHF", round(by_name["chf"].sum(), 2))
unloc_co = ino[ino["npa"].isna() & ino["is_company"] & ~ino["k"].isin(co_index)]
log("ARAMIS : projets dont le contact est une entreprise sans adresse", len(unloc_co), "| CHF", round(unloc_co["chf"].sum()))

cordis_pos = {o["name"]: (o["lat"], o["lon"]) for o in orgs.values() if o["lat"] and o["name"] in CAT_BY_CANON}
ino_orgs, ino_projects = {}, {}
for _, r in ivd.iterrows():
    c = r["canon"] or "Organisation non identifiée"
    key = "I" + re.sub(r"\W+", "_", c)[:60]
    if key not in ino_orgs:
        if c in POS_OVERRIDE:
            ll = POS_OVERRIDE[c]; bfs = commune_of(*ll)
        elif c in cordis_pos and (r["vd_by_name"] or r["npa"] == HQ_NPA.get(c)):
            ll = cordis_pos[c]; bfs = commune_of(*ll)
        else:
            ll, bfs = locate(None, r["npa"] or HQ_NPA.get(c), r["city"])
        typ = CAT_BY_CANON.get(c, EN if r["is_company"] else (HE if re.search(r"UNIVERSIT", c, re.I) else
                              (RI if re.search(r"INSTITUT|CENTRE|CENTER", c, re.I) else AU)))
        ino_orgs[key] = {"id": key, "name": c, "type": typ, "bfs": bfs,
                         "lat": round(ll[0], 5) if ll else None, "lon": round(ll[1], 5) if ll else None, "src": "INNO"}
    title = next((t for t in [r["Projekttitel französisch"], r["Projekttitel englisch"], r["Projekttitel deutsch"]]
                  if isinstance(t, str) and t.strip()), "")
    ino_projects["I" + r["Projektnummer"]] = {"o": key, "num": r["Projektnummer"], "t": title, "y": int(r["start"].year),
                                             "chf": round(float(r["chf"]), 2), "dom": r["dom"], "instr": r["instr"],
                                             "pos": "siège" if r["vd_by_name"] else "adresse"}
log("ARAMIS : organisations vaudoises", len(ino_orgs), "| sans commune", [o["name"] for o in ino_orgs.values() if o["bfs"] is None])
log("ARAMIS : organisations", sorted(((Counter(p["o"] for p in ino_projects.values())[k], o["name"], o["type"])
                                     for k, o in ino_orgs.items()), reverse=True))
for _, r in by_name.iterrows():
    title = next((t for t in [r["Projekttitel französisch"], r["Projekttitel englisch"], r["Projekttitel deutsch"]]
                  if isinstance(t, str) and t.strip()), "")
    ino_projects["I" + r["Projektnummer"]] = {"o": co_index[r["k"]], "num": r["Projektnummer"], "t": title, "y": int(r["start"].year),
                                             "chf": round(float(r["chf"]), 2), "dom": r["dom"], "instr": r["instr"], "pos": "nom"}
ivd = pd.concat([ivd, by_name])
ino_years = {int(y): {"n": int(len(g)), "chf": round(float(g["chf"].sum()), 2)} for y, g in ivd.groupby(ivd["start"].dt.year)}

# ---------- Innosuisse : participants collectés (tous les partenaires, avec numéro IDE) ----------
import os
PART = os.environ.get("INNO_PART", f"{BASE}/data/state/innosuisse_participants.csv")
SIEGES = os.environ.get("INNO_SIEGES", f"{BASE}/data/state/ide_sieges.csv")
ino_fed, ino_mode, ino_stats = None, "contact", None
def participants_complete(path):
    """N'utilise la collecte des participants que si elle couvre presque tous les projets Innosuisse (sinon vue partielle)."""
    if not os.path.exists(path): return False
    got = set(pd.read_csv(path, dtype=str, usecols=["ProjectNumber"])["ProjectNumber"])
    share = len(got & set(ino["Projektnummer"])) / max(1, len(ino))
    log(f"Innosuisse : participants collectés pour {share:.1%} des projets 2018+")
    return share >= float(os.environ.get("INNO_SEUIL", "0.95"))
if participants_complete(PART):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import innosuisse_partners as IP
    m_all = shapefile.Reader(f"{BASE}/node_modules/swiss-maps/2026/municipalities")
    code_of = {v: k for k, v in CANTON_ID.items()}
    muni_canton = {int(r["id"]): code_of.get(int(r["KTNR"])) for r in m_all.records() if r["id"]}
    cordis_ch = [(r["name"], r["canton"]) for _, r in ch.dropna(subset=["canton"]).drop_duplicates("organisationID").iterrows()]
    learned = IP.learn_from_contacts(zip(ino["org"], ino["npa"]), zip_ref, cordis_ch)
    vd_geom_by_id = dict(zip(vd_ids, vd_geoms))
    def vd_locate(pc, town, bfs, name):
        c = canon(name)
        if c in POS_OVERRIDE: ll = POS_OVERRIDE[c]; return ll, commune_of(*ll)
        if c in cordis_pos: ll = cordis_pos[c]; return ll, commune_of(*ll)
        if c in HQ_NPA and not pc: pc = HQ_NPA[c]
        ll, b2 = locate(None, pc, town)
        if b2: return ll, b2
        if bfs in vd_geom_by_id:
            pt = vd_geom_by_id[bfs].representative_point(); return (pt.y, pt.x), bfs
        return None, None
    fed, vd_orgs2, vd_projects2, meta, ino_stats = IP.build(PART, SIEGES if os.path.exists(SIEGES) else None, ino, zip_ref,
                                                            muni_canton, vd_locate, learned, log)
    for o in vd_orgs2.values():
        c = canon(o["name"])
        if o["type"] is None:
            o["type"] = CAT_BY_CANON.get(c, HE if re.search(r"UNIVERSIT|HOCHSCHULE|HAUTE|ECOLE|ÉCOLE", o["name"], re.I) else
                                         (RI if re.search(r"INSTITUT|CENTRE|CENTER", o["name"], re.I) else AU))
        if c in CAT_BY_CANON: o["name"] = c
    ino_orgs = vd_orgs2
    ino_projects = {}
    for num, lst in vd_projects2.items():
        r = meta.loc[num]
        title = next((t for t in [r["Projekttitel französisch"], r["Projekttitel englisch"], r["Projekttitel deutsch"]]
                      if isinstance(t, str) and t.strip()), "")
        ino_projects["I" + num] = {"os": [[o, role] for o, role in lst], "num": num, "t": title, "y": int(r["start"].year),
                                   "chf": round(float(r["chf"]), 2), "np": int(r["np"]) if r["np"] == r["np"] else 1,
                                   "dom": r["dom"], "instr": r["instr"], "pos": "participant"}
    ivd = ino[ino["Projektnummer"].isin(vd_projects2)]
    ino_years = {int(y): {"n": int(len(g)), "chf": round(float(g["chf"].sum()), 2)} for y, g in ivd.groupby(ivd["start"].dt.year)}
    ino_fed, ino_mode = fed, "participants"
    unloc_co = ino.iloc[0:0]
    log("CONTRÔLE : Innosuisse VD (participants)", len(ino_projects), "projets | CHF", round(float(ivd["chf"].sum()), 2),
        "| projets sans organisation positionnée", sum(1 for pj in ino_projects.values() if all(ino_orgs[o]["lat"] is None for o, _ in pj["os"])))

# ---------- Assemblage ----------
communes = {b: {"name": names.get(b, str(b)), "district": d} for b, d in vd_dist.items()}
def pack(row):
    return {"eu_n": int(row["n"]), "eu_funded": int(row["funded"]), "eu_ec": round(float(row["ec"]), 2),
            "coord": int(row["coord"]), "assoc": int(row["assoc"]), "prc": int(row["prc"]), "sme": int(row["sme"]),
            "orgs": int(row["orgs"]), "projects": int(row["projects"])}
EMPTY = {"eu_n": 0, "eu_funded": 0, "eu_ec": 0, "coord": 0, "assoc": 0, "prc": 0, "sme": 0, "orgs": 0, "projects": 0}
cantons = {cid: {"code": code, **(pack(cant_eu.loc[code]) if code in cant_eu.index else EMPTY)} for code, cid in CANTON_ID.items()}
countries = {("GR" if k == "EL" else "GB" if k == "UK" else k): pack(r) for k, r in ctry.iterrows()}
ISO_FIX = {"EL": "GR", "UK": "GB"}
data = {"generated": pd.Timestamp.now(tz="Europe/Zurich").strftime("%Y-%m-%d"),
        "orgs": list(orgs.values()) + list(ino_orgs.values()),
        "eu_parts": parts, "eu_projects": eu_projects, "ino_projects": ino_projects,
        "ino_fed": ino_fed, "ino_mode": ino_mode, "ino_stats": ino_stats, "hesso": hesso,
        "communes": communes, "cantons": cantons, "countries": countries, "bench": bench, "pop": pop, "partners_by_year": partners_by_year,
        "partner_countries": {ISO_FIX.get(k, k): v for k, v in partner_countries.items()},
        "eu_years": eu_years, "ino_years": ino_years,
        "ino_unlocated": {"companies_n": int(len(unloc_co)), "companies_chf": round(float(unloc_co["chf"].sum()), 2)},
        "ch_totals": {"eu_n": int(len(ch)), "eu_funded": int((ch["ec"] > 0).sum()),
                      "eu_assoc": int((ch["role"] == "associatedPartner").sum()), "eu_ec": round(float(ch["ec"].sum()), 2),
                      "ino_n": int(len(ino)), "ino_chf": round(float(ino["chf"].sum()), 2)}}
json.dump(data, open(f"{B}/data.json", "w"), ensure_ascii=False, separators=(",", ":"))

# ---------- Contrôles ----------
log("CONTRÔLE : UE vers VD", round(sum(p["ec"] for p in parts), 2), "= source", round(float(vd["ec"].sum()), 2))
if ino_mode == "contact": log("CONTRÔLE : CHF Innosuisse VD", round(sum(p["chf"] for p in ino_projects.values()), 2), "= source",
    round(float(ivd["chf"].sum()), 2), "| projets distincts", len(ino_projects), "= lignes", len(ivd))
log("CONTRÔLE : rôles VD", dict(Counter(p["role"] for p in parts)))
log("CONTRÔLE : participations VD sans projet connu", sum(1 for p in parts if p["p"] not in eu_projects))
open(f"{B}/qa.txt", "w").write("\n".join(qa))
