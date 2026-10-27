"""Attribue un numéro IDE (registre du commerce) aux organisations qui n'en ont pas, à partir de leur raison sociale.

Sources :
  data/state/registre/registre_vd.csv.gz   entités à siège vaudois (Zefix sur LINDAS, scripts/registre_extrait.py)
  data/state/registre/recherche.csv        recherche par nom dans toute la Suisse
  data/state/ide_sieges.csv                sièges des numéros IDE connus (nom de commune <-> numéro OFS)

Sorties :
  data/ref/ide_correspondances.csv   organisations de l'atlas sans IDE (Innosuisse, UE) -> IDE
  <--sortie-scaleups>                scale-ups suivies -> IDE (référentiel commun)
  build/ide_controle.txt             précision mesurée sur les partenaires Innosuisse dont l'IDE est connu

Confiance : haute (raison sociale identique, une seule entité, siège cohérent), moyenne (identique hors mots génériques,
ou siège différent), basse (proche mais pas identique, ou plusieurs candidats) : à valider. Une ligne validée à la main
(colonne valide = OUI ou NON) n'est jamais écrasée.
Usage : python scripts/referentiel_ide.py --scaleups ../scaleups/data/referentiel_entreprises.csv --sortie-scaleups ...
"""
import argparse, csv, gzip, json, os, re, unicodedata
from collections import defaultdict


FORMES = (r"\b(s a r l|sarl|s a|sa|ag|gmbh|ltd|limited|inc|llc|sas|srl|plc|bv|kg|co|cie|en liquidation|in liquidation"
          r"|in liq|en liq|i l|in liquidazione|en faillite|in konkurs)\b")
GENERIQUES = r"\b(holding|group|groupe|international|switzerland|suisse|schweiz|svizzera|swiss|europe|the)\b"
SUCCURSALE = r"succursale|zweigniederlassung|filiale|branch|niederlassung"


def sans_accents(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def coeur(s, generiques=False):
    s = sans_accents(s)
    s = re.sub(r"che[\s-]*\d{3}[.\s]?\d{3}[.\s]?\d{3}", " ", s)          # numéro IDE collé au nom
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(FORMES, " ", s)
    if generiques:
        s = re.sub(GENERIQUES, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def uid_dans(s):
    m = re.search(r"CHE[\s-]*(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})", s or "", re.I)
    return "CHE" + "".join(m.groups()) if m else ""


class Registre:
    def __init__(self, base="data/state"):
        self.ent = {}                                    # uid -> {noms, bfs}
        def ajoute(uid, nom, bfs, forme=""):
            e = self.ent.setdefault(uid, {"noms": set(), "bfs": bfs, "forme": forme})
            e["noms"].add(nom)
            e["bfs"] = e["bfs"] or bfs
        p = f"{base}/registre/registre_vd.csv.gz"
        if os.path.exists(p):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    ajoute(r["UID"], r["Name"], r["MunicipalityBFS"], r.get("LegalForm", ""))
        self.vd = set(self.ent)
        p = f"{base}/registre/recherche.csv"
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8")):
                ajoute(r["UID"], r["Name"], r["MunicipalityBFS"])
        p = f"{base}/ide_sieges.csv"
        self.commune_bfs = {}
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8-sig")):
                if r["Name"]:
                    ajoute(r["UID"], r["Name"], r["MunicipalityBFS"])
                if r["Municipality"] and r["MunicipalityBFS"]:
                    self.commune_bfs[sans_accents(r["Municipality"])] = r["MunicipalityBFS"]
        self.idx1, self.idx2 = defaultdict(set), defaultdict(set)
        for u, e in self.ent.items():
            for n in e["noms"]:
                if re.search(SUCCURSALE, n, re.I):
                    continue
                self.idx1[coeur(n)].add(u)
                self.idx2[coeur(n, True)].add(u)
        self.cles_vd = sorted({coeur(n) for u in self.vd for n in self.ent[u]["noms"]} - {""})
        print(f"Registre : {len(self.ent)} entités ({len(self.vd)} à siège vaudois), {len(self.idx1)} raisons sociales")

    def nom(self, u):
        return sorted(self.ent[u]["noms"], key=len)[0] if u in self.ent else ""

    def bfs(self, u):
        return self.ent.get(u, {}).get("bfs", "")

    def chercher(self, noms, bfs=None, vaudois=True):
        """Renvoie (uid, confiance, méthode, autres candidats)."""
        noms = [n for n in noms if n]
        for n in noms:
            u = uid_dans(n)
            if u:
                return u, "haute", "numéro dans le nom", []

        def tri(cands):
            # siège dans la commune indiquée, puis dans le canton, puis ailleurs
            return sorted(cands, key=lambda u: (self.bfs(u) != bfs if bfs else True, u not in self.vd, u))

        for niveau, idx, gen in [("identique", self.idx1, False), ("identique hors mots génériques", self.idx2, True)]:
            cands = set()
            for n in noms:
                c = coeur(n, gen)
                if len(c) >= 3:
                    cands |= idx.get(c, set())
            if not cands:
                continue
            cands = tri(cands)
            u = cands[0]
            siege_ok = (self.bfs(u) == bfs) if bfs else (u in self.vd or not vaudois)
            if len(cands) == 1:
                conf = "haute" if (niveau == "identique" and siege_ok) else "moyenne"
                return u, conf, niveau, []
            # plusieurs entités du même nom : une seule dans la commune indiquée suffit
            if bfs and sum(self.bfs(x) == bfs for x in cands) == 1:
                return u, "moyenne", niveau + ", plusieurs entités (commune décisive)", cands[1:4]
            return u, "basse", niveau + ", plusieurs entités", cands[1:4]
        # nom proche parmi les entités vaudoises
        from rapidfuzz import fuzz, process
        best = None
        for n in noms:
            c = coeur(n)
            if len(c) < 4:
                continue
            for cle, score, _ in process.extract(c, self.cles_vd, scorer=fuzz.ratio, limit=3):
                if score >= 90 and (best is None or score > best[1]):
                    best = (cle, score)
        if best:
            cands = tri(self.idx1.get(best[0], set()))
            if cands:
                return cands[0], "basse", f"nom proche ({best[1]:.0f} %)", cands[1:4]
        return "", "aucune", "", []


def lire_csv(p, delim=","):
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=delim))


def ecrire_csv(p, champs, lignes, delim=","):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=delim, extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)


def controle(reg):
    """Précision mesurée : on cache l'IDE des partenaires Innosuisse vaudois qui en ont un, et on le retrouve par le nom."""
    vus, ok, faux, rien = set(), defaultdict(int), defaultdict(list), 0
    for r in lire_csv("data/state/innosuisse_participants.csv"):
        if r["Canton"] != "VD" or not re.fullmatch(r"CHE\d{9}", r["UID"] or "") or r["UID"] in vus:
            continue
        vus.add(r["UID"])
        nom = re.sub(r"CHE[\s-]*\d{3}[.\s]?\d{3}[.\s]?\d{3}", "", r["Company"])
        u, conf, meth, _ = reg.chercher([nom], reg.commune_bfs.get(sans_accents(r["City"])))
        if not u:
            rien += 1
        elif u == r["UID"]:
            ok[conf] += 1
        else:
            faux[conf].append((r["Company"], r["UID"], u, reg.nom(u)))
    lignes = [f"Contrôle sur {len(vus)} partenaires Innosuisse vaudois dont l'IDE est connu :"]
    for conf in ["haute", "moyenne", "basse"]:
        n = ok[conf] + len(faux[conf])
        if n:
            lignes.append(f"  confiance {conf} : {ok[conf]}/{n} justes ({ok[conf] / n:.1%})")
    lignes.append(f"  sans candidat : {rien}")
    for conf in ["haute", "moyenne"]:
        for x in faux[conf][:15]:
            lignes.append(f"  erreur ({conf}) : {x}")
    os.makedirs("build", exist_ok=True)
    open("build/ide_controle.txt", "w", encoding="utf-8").write("\n".join(lignes) + "\n")
    print("\n".join(lignes[:6]))


def atlas(reg, sortie="data/ref/ide_correspondances.csv"):
    """Organisations de l'atlas sans IDE : partenaires Innosuisse vaudois sans numéro, participants UE sans numéro TVA."""
    anciens = {r["cle"]: r for r in lire_csv(sortie) if r.get("valide") in ("OUI", "NON")}
    a_faire = {}
    for r in lire_csv("data/state/innosuisse_participants.csv"):
        if r["UID"] or r["Canton"] != "VD" or uid_dans(r["Company"]):
            continue
        cle = "INNO:" + coeur(r["Company"])
        a_faire.setdefault(cle, (r["Company"], r["City"], r["PostCode"]))
    try:
        import pandas as pd
        for f in ["organization", "h2020_organization"]:
            p = f"data/cache/{f}.pkl"
            if not os.path.exists(p):
                continue
            o = pd.read_pickle(p)
            o = o[(o["country"] == "CH") & o["postCode"].astype(str).str.match(r"1[0-9]{3}")]
            for _, r in o.iterrows():
                if uid_dans(str(r["vatNumber"])):
                    continue
                cle = "EU:" + str(r["organisationID"]).split(".")[0]
                a_faire.setdefault(cle, (str(r["name"]), str(r["city"]), str(r["postCode"])))
    except ImportError:
        pass
    lignes = []
    for cle, (nom, ville, npa) in sorted(a_faire.items()):
        if cle in anciens:
            lignes.append(anciens[cle]); continue
        u, conf, meth, autres = reg.chercher([nom], reg.commune_bfs.get(sans_accents(ville)))
        lignes.append({"cle": cle, "nom_source": nom, "npa": npa, "localite": ville, "uid": u, "nom_registre": reg.nom(u),
                       "bfs_registre": reg.bfs(u), "confiance": conf, "methode": meth,
                       "autres_candidats": " | ".join(f"{x} {reg.nom(x)}" for x in autres), "valide": ""})
    ecrire_csv(sortie, ["cle", "nom_source", "npa", "localite", "uid", "nom_registre", "bfs_registre", "confiance",
                        "methode", "autres_candidats", "valide"], lignes)
    n = defaultdict(int)
    for l in lignes:
        n[l["confiance"]] += 1
    print(f"Atlas : {len(lignes)} organisations sans IDE -> {dict(n)}")


def scaleups(reg, src, sortie):
    anciens = {r["company"]: r for r in lire_csv(sortie, ";") if r.get("uid_valide") in ("OUI", "NON")}
    lignes = []
    for r in lire_csv(src, ";"):
        if r["company"] in anciens:
            lignes.append(anciens[r["company"]]); continue
        bfs = reg.commune_bfs.get(sans_accents(r["siege_commune"])) if r["siege_commune"] else None
        u = uid_dans(r.get("note", "")) or uid_dans(r.get("source", ""))
        if u:
            conf, meth, autres = "haute", "numéro noté dans le référentiel", []
        else:
            u, conf, meth, autres = reg.chercher([r["raison_sociale"], r["company"]], bfs, vaudois=r["siege_canton"] in ("", "VD"))
        lignes.append({**{k: r[k] for k in ("company", "raison_sociale", "siege_commune", "siege_canton", "perimetre", "statut_registre")},
                       "uid": u, "nom_registre": reg.nom(u), "bfs_registre": reg.bfs(u), "confiance": conf, "methode": meth,
                       "autres_candidats": " | ".join(f"{x} {reg.nom(x)}" for x in autres), "uid_valide": ""})
    ecrire_csv(sortie, ["company", "raison_sociale", "siege_commune", "siege_canton", "perimetre", "statut_registre", "uid",
                        "nom_registre", "bfs_registre", "confiance", "methode", "autres_candidats", "uid_valide"], lignes, ";")
    n = defaultdict(int)
    for l in lignes:
        n[l["confiance"]] += 1
    print(f"Scale-ups : {len(lignes)} lignes -> {dict(n)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaleups"); ap.add_argument("--sortie-scaleups")
    a = ap.parse_args()
    reg = Registre()
    controle(reg)
    atlas(reg)
    if a.scaleups and a.sortie_scaleups:
        scaleups(reg, a.scaleups, a.sortie_scaleups)


if __name__ == "__main__":
    main()
