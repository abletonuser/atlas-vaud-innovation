"""Exploitation des participants Innosuisse collectés dans ARAMIS (innosuisse_participants.csv)
et des sièges d'entreprises retrouvés par leur numéro IDE (ide_sieges.csv).

Fournit build(...) qui renvoie :
  - fed : lignes [canton_id, année, côté, projets, CHF] pour la vue fédérale
          côté 0 = au moins une entreprise partenaire du canton ; 1 = au moins un partenaire de recherche du canton ;
          2 = au moins un partenaire du canton (toutes catégories)
  - vd_orgs, vd_projects : organisations et projets vaudois pour la carte du canton
  - stats : contrôles de couverture
"""
import re, unicodedata
from collections import Counter, defaultdict
import pandas as pd

CANTON_ID = {"ZH": 1, "BE": 2, "LU": 3, "UR": 4, "SZ": 5, "OW": 6, "NW": 7, "GL": 8, "ZG": 9, "FR": 10, "SO": 11, "BS": 12,
             "BL": 13, "SH": 14, "AR": 15, "AI": 16, "SG": 17, "GR": 18, "AG": 19, "TG": 20, "TI": 21, "VD": 22, "VS": 23,
             "NE": 24, "GE": 25, "JU": 26}
BUSINESS_ROLE = re.compile(r"(partenaire commercial|wirtschaftspartner|umsetzungspartner|partenaire de mise en|implementation partner|business partner)", re.I)
RESEARCH_NAME = r"universit|hochschule|haute [ée]cole|[ée]cole|school|institut|spital|h[ôo]pital|clinique|klinik|insel gruppe|innovation park|rhysearch|m4m center|forschung|laborator|fondation|stiftung|foundation|verein|association|\bcentre\b|\bcenter\b|zentrum"
NOT_COMPANY = r"\b(association|verein|fondation|stiftung|foundation|commune|gemeinde|ville de|stadt |canton|kanton|universit|hochschule|haute [ée]cole|[ée]cole|spital|h[ôo]pital|clinique|chuv|institut)\b"
COMPANY_FORM = re.compile(r"\b(SA|AG|GmbH|S[àa]rl|SARL|Sagl|Ltd|Inc|SE|KG)\b")

# Institutions de recherche : mots-clés -> canton (siège ou site principal). Les cas ambigus restent sans canton.
RESEARCH_RULES = [
    (r"\bEPFL\b|polytechnique f[ée]d[ée]rale de lausanne", "VD"), (r"\bETH\b|ETHZ|eidgen[öo]ssische technische hochschule", "ZH"),
    (r"universit[äa]t z[üu]rich|\bUZH\b", "ZH"), (r"\bZHAW\b|z[üu]rcher hochschule f[üu]r angewandte", "ZH"), (r"\bZHdK\b", "ZH"),
    (r"\bBFH\b|berner fachhochschule", "BE"), (r"universit[äa]t bern|university of bern|\bUNIBE\b", "BE"), (r"\bPH ?Bern\b", "BE"),
    (r"\bHSLU\b|hochschule luzern", "LU"), (r"universit[äa]t luzern", "LU"), (r"\bOST\b.*fachhochschule|ostschweizer fachhochschule", "SG"),
    (r"universit[äa]t st\.? ?gallen|\bHSG\b", "SG"), (r"\bSUPSI\b", "TI"), (r"universit[àa] della svizzera italiana|\bUSI\b", "TI"),
    (r"\bIDSIA\b", "TI"), (r"universit[ée] de gen[èe]ve|\bUNIGE\b", "GE"), (r"\bHEPIA\b|\bHEG[- ]?GE\b|HES-SO Gen[èe]ve", "GE"),
    (r"universit[ée] de lausanne|\bUNIL\b", "VD"), (r"\bHEIG\b|ing[ée]nierie et de gestion du canton de vaud", "VD"),
    (r"\bCHUV\b", "VD"), (r"unisant[ée]", "VD"), (r"\bEHL\b|[ée]cole h[ôo]teli[èe]re de lausanne", "VD"), (r"\bECAL\b", "VD"),
    (r"\bHESAV\b", "VD"), (r"\bHETSL\b|\bEESP\b", "VD"), (r"la source", "VD"), (r"changins", "VD"), (r"\bIMD\b", "VD"),
    (r"\bHE-?Arc\b", "NE"), (r"universit[ée] de neuch[âa]tel", "NE"), (r"\bCSEM\b", "NE"),
    (r"HES-SO\W*Valais|\bHEVS\b|hochschule wallis|HETS-VS", "VS"), (r"\bIdiap\b", "VS"),
    (r"\bHEIA[- ]?FR\b|haute [ée]cole d'ing[ée]nierie et d'architecture de fribourg|HES-SO Fribourg", "FR"),
    (r"universit[ée] de fribourg|universit[äa]t freiburg|\bUNIFR\b", "FR"),
    (r"universit[äa]t basel|\bUNIBAS\b", "BS"), (r"\bFHNW\b|fachhochschule nordwestschweiz", "AG"),
    (r"\bEmpa\b", "ZH"), (r"\bEawag\b", "ZH"), (r"\bPSI\b|paul scherrer", "AG"), (r"\bWSL\b", "ZH"), (r"\bSLF\b", "GR"),
    (r"\bAgroscope\b", "BE"), (r"\bFiBL\b", "AG"), (r"\bINSPIRE AG\b", "ZH"), (r"\bIRB\b|institute for research in biomedicine", "TI"),
    (r"\bWITg\b|werkstoffsystemtechnik thurgau", "TG"), (r"\bIOR\b|institute of oncology research", "TI"),
    (r"versuchsstollen hagerbach", "SG"), (r"swiss TPH|tropical and public health", "BL"), (r"\bUKBB\b|kinderspital beider basel|kinderspital basel", "BS"),
    (r"\bPH-?SG\b|p[äa]dagogische hochschule st\.? ?gallen", "SG"), (r"\bPH-?ZH\b|p[äa]dagogische hochschule z[üu]rich", "ZH"),
    (r"\bPHTG\b|p[äa]dagogische hochschule thurgau", "TG"), (r"\bPH ?LU\b|p[äa]dagogische hochschule luzern|PH Luzern", "LU"),
    (r"p[äa]dagogische hochschule schwyz", "SZ"), (r"p[äa]dagogische hochschule zug|PH Zug", "ZG"),
    (r"HEP[- ]Vaud|haute [ée]cole p[ée]dagogique du canton de vaud", "VD"), (r"HEP[- ]Fribourg", "FR"), (r"HEP[- ]Valais", "VS"),
    (r"\bFHGR\b|fachhochschule graub[üu]nden", "GR"), (r"\bFFHS\b|fernfachhochschule", "VS"), (r"\bSDSC\b|swiss data science", "ZH"),
]

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def research_canton(name, learned):
    if not isinstance(name, str) or not name.strip():
        return None
    for pat, c in RESEARCH_RULES:
        if re.search(pat, name, re.I):
            return c
    k = norm(name)
    if k in learned:
        return learned[k]
    head = norm(name.split(" - ")[0])
    return learned.get(head)

def learn_from_contacts(ino_contacts, zip_ref, cordis_ch):
    """Nom d'organisation -> canton, appris des contacts ARAMIS avec adresse et des organisations suisses de CORDIS."""
    votes = defaultdict(Counter)
    for org, npa in ino_contacts:
        if isinstance(org, str) and npa in zip_ref:
            votes[norm(org)][zip_ref[npa]["state_code"]] += 1
    for name, canton in cordis_ch:
        if isinstance(name, str) and canton:
            votes[norm(name)][canton] += 1
    return {k: c.most_common(1)[0][0] for k, c in votes.items() if c and c.most_common(1)[0][1] >= 1}

def correspondances(path="data/ref/ide_correspondances.csv"):
    """clé (INNO:raison sociale | EU:PIC) -> IDE, pour les correspondances sûres (confiance haute ou validées OUI)."""
    import csv, os
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["cle"]: r["uid"] for r in csv.DictReader(f)
                if r["uid"] and r.get("valide") != "NON" and (r["confiance"] == "haute" or r.get("valide") == "OUI")}


def build(part_csv, sieges_csv, ino, zip_ref, muni_canton, vd_locate, learned, log):
    p = pd.read_csv(part_csv, dtype=str).fillna("")
    s = pd.read_csv(sieges_csv, dtype=str).fillna("") if sieges_csv else pd.DataFrame(columns=["UID"])
    seat = {r["UID"]: r for _, r in s.iterrows()}
    # numéro IDE parfois collé au nom (« Sonova AG CHE-101.989.881 ») : on le sépare
    emb = p["Company"].str.extract(r"CHE-?(\d{3})\.?(\d{3})\.?(\d{3})")
    has = emb.notna().all(axis=1) & (p["UID"] == "")
    p.loc[has, "UID"] = "CHE" + emb[0] + emb[1] + emb[2]
    p["Company"] = p["Company"].str.replace(r"\s*,?\s*CHE-?\d{3}\.?\d{3}\.?\d{3}\s*", " ", regex=True).str.strip()
    # numéro IDE retrouvé par la raison sociale (scripts/referentiel_ide.py) : confiance haute, ou validé à la main.
    # Il sert à l'identité (UIDC) : une même entreprise saisie avec et sans numéro n'est plus comptée deux fois.
    # La localisation reste celle publiée par ARAMIS (UID publié et son siège, sinon adresse du partenaire).
    p["UIDC"] = p["UID"]
    corr = correspondances()
    if corr:
        from referentiel_ide import coeur
        sans = (p["UID"] == "") & (p["Canton"] == "VD")
        trouve = p.loc[sans, "Company"].map(lambda n: corr.get("INNO:" + coeur(n), ""))
        p.loc[trouve.index, "UIDC"] = trouve
        log("Innosuisse : IDE retrouvés par la raison sociale (VD)", int((trouve != "").sum()), "lignes sur", int(sans.sum()))
    # côté entreprise = rôle « partenaire commercial / de mise en œuvre » publié par ARAMIS. Un numéro IDE seul ne suffit pas :
    # des instituts de recherche (CSEM, SUPSI, inspire…) en ont un et figurent comme contact ou direction scientifique.
    # Contact ou direction scientifique : institution de recherche, sauf entreprise (IDE ou forme juridique) au nom non
    # académique, par exemple une start-up requérante d'un projet sans partenaire de recherche.
    biz_role = p["KindOfParticipation"].apply(lambda k: bool(BUSINESS_ROLE.search(k)))
    research_name = p["Company"].apply(lambda n: bool(re.search(RESEARCH_NAME, n, re.I)) or any(re.search(pt, n, re.I) for pt, _ in RESEARCH_RULES))
    companyish = (p["UID"] != "") | p["Company"].apply(lambda n: bool(COMPANY_FORM.search(n)))
    p["is_business"] = biz_role | (~research_name & companyish)
    # une même organisation peut figurer deux fois (contact et direction scientifique) : on dédoublonne par projet
    p["key"] = p.apply(lambda r: r["UIDC"] or norm(r["Company"]), axis=1)
    # une organisation compte une fois par projet ; si elle est à la fois contact et partenaire commercial, côté entreprise
    p = p[p["key"] != ""].sort_values("is_business", ascending=False).drop_duplicates(["ProjectNumber", "key"])

    def canton_of(r):
        if r["UID"] and r["UID"] in seat:
            z = seat[r["UID"]]
            bfs = z.get("MunicipalityBFS", "")
            if bfs and bfs.isdigit() and int(bfs) in muni_canton:
                return muni_canton[int(bfs)]
            pc = z.get("PostCode", "")[:4]
            if pc in zip_ref:
                return zip_ref[pc]["state_code"]
            return None
        if r["PostCode"][:4] in zip_ref:
            return zip_ref[r["PostCode"][:4]]["state_code"]
        if r["is_business"]:
            return None
        return research_canton(r["Company"], learned)
    p["canton"] = p.apply(canton_of, axis=1)

    meta = ino.set_index("Projektnummer")[["chf", "start", "instr", "dom", "Projekttitel französisch", "Projekttitel englisch", "Projekttitel deutsch"]]
    p = p[p["ProjectNumber"].isin(meta.index)].copy()
    p["year"] = p["ProjectNumber"].map(meta["start"]).dt.year
    p["chf"] = p["ProjectNumber"].map(meta["chf"])

    bus, res = p[p["is_business"]], p[~p["is_business"]]
    stats = {"projets": int(p["ProjectNumber"].nunique()),
             "entreprises": int(bus["key"].nunique()), "entreprises_localisees": int(bus.loc[bus["canton"].notna(), "key"].nunique()),
             "recherche": int(res["key"].nunique()), "recherche_localisee": int(res.loc[res["canton"].notna(), "key"].nunique())}
    log("Innosuisse participants :", stats)
    log("Innosuisse : institutions de recherche sans canton (top)", Counter(res.loc[res["canton"].isna(), "Company"]).most_common(12))

    # Montant attribué (comptage fractionnaire) : le coût approuvé d'un projet est réparti à parts égales entre ses
    # partenaires ; un canton reçoit la part de ses partenaires. Aucun franc n'est compté deux fois entre cantons.
    p["np"] = p.groupby("ProjectNumber")["key"].transform("size")
    p["share"] = p["chf"] / p["np"]
    bus, res = p[p["is_business"]], p[~p["is_business"]]
    fed = []
    for side, df in [(0, bus), (1, res), (2, p)]:
        g = df.dropna(subset=["canton"])
        for (c, y), gg in g.groupby(["canton", "year"]):
            if c in CANTON_ID:
                fed.append([CANTON_ID[c], int(y), side, int(gg["ProjectNumber"].nunique()), round(float(gg["share"].sum()), 2),
                            round(float((1 / gg["np"]).sum()), 3)])
    tot = p.drop_duplicates("ProjectNumber")["chf"].sum()
    att = p.loc[p["canton"].isin(CANTON_ID), "share"].sum()
    stats["chf_total"] = round(float(tot), 2); stats["chf_cantons"] = round(float(att), 2)
    log(f"Innosuisse : coûts attribués aux cantons {att:,.0f} sur {tot:,.0f} CHF ({att / tot:.1%}) ; reste : partenaires étrangers ou non localisés")
    meta = meta.copy(); meta["np"] = p.groupby("ProjectNumber").size()

    vd = p[p["canton"] == "VD"]
    vd_orgs, vd_projects = {}, defaultdict(list)
    for _, r in vd.iterrows():
        oid = "IU" + r["UIDC"] if r["UIDC"] else "IR" + re.sub(r"\W+", "_", norm(r["Company"]))[:50]
        if oid not in vd_orgs:
            z = seat.get(r["UID"]) if r["UID"] else None
            name = (z["Name"] if z is not None and z["Name"] else r["Company"])
            ll, bfs = vd_locate(z["PostCode"][:4] if z is not None else r["PostCode"][:4],
                                z["Town"] if z is not None else r["City"],
                                int(z["MunicipalityBFS"]) if z is not None and str(z["MunicipalityBFS"]).isdigit() else None,
                                name)
            not_co = re.search(NOT_COMPANY, name or "", re.I)
            vd_orgs[oid] = {"id": oid, "name": name, "type": "Entreprise" if r["is_business"] and not not_co else None, "uid": r["UIDC"],
                            "bfs": bfs, "lat": round(ll[0], 5) if ll else None, "lon": round(ll[1], 5) if ll else None, "src": "INNO"}
        vd_projects[r["ProjectNumber"]].append((oid, "entreprise" if r["is_business"] else "recherche"))
    log("Innosuisse VD : projets", len(vd_projects), "| organisations", len(vd_orgs),
        "| entreprises", sum(1 for o in vd_orgs.values() if o["type"] == "Entreprise"))
    return fed, vd_orgs, vd_projects, meta, stats
