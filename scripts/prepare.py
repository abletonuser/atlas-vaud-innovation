"""Convertit les fichiers téléchargés (data/raw) en tables prêtes pour build_data.py (data/cache, non versionné).

Les CSV CORDIS ont des champs entre guillemets séparés par ";" mais des guillemets non échappés dans les textes
libres : on découpe donc chaque enregistrement sur '";"' (lecture vérifiée sans perte sur H2020).
Accepte aussi les exports Excel (.xlsx) de CORDIS, téléchargés à la main.
Usage : python scripts/prepare.py [dossier du dépôt]
"""
import os, re, sys
import pandas as pd

BASE = sys.argv[1] if len(sys.argv) > 1 else "."
RAW, CACHE = os.path.join(BASE, "data", "raw"), os.path.join(BASE, "data", "cache")
START = re.compile(r'^"\d+";"')


def read_cordis_csv(path, first_n=None):
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline().strip().strip('"').split('";"')
        rows, bad = [], 0
        for line in f:
            if not START.match(line):
                continue                                   # suite d'un texte libre sur plusieurs lignes
            line = line.rstrip("\n").rstrip("\r").strip()
            parts = line[1:].split('";"') if first_n else line[1:-1].split('";"')
            if first_n:
                if len(parts) >= first_n:
                    rows.append(dict(zip(header[:first_n], parts[:first_n])))
                else:
                    bad += 1
            elif len(parts) == len(header):
                rows.append(dict(zip(header, parts)))
            else:
                bad += 1
    print(f"  {os.path.basename(path)} : {len(rows)} lignes, {bad} rejetées")
    if bad > 0.01 * max(1, len(rows)):
        raise SystemExit(f"Trop de lignes rejetées dans {path}")
    return pd.DataFrame(rows)


def load(key, name, first_n=None):
    d = os.path.join(RAW, key)
    if os.path.exists(os.path.join(d, name + ".csv")):
        if name == "euroSciVoc":
            return pd.read_csv(os.path.join(d, name + ".csv"), sep=";", dtype=str, quotechar='"', on_bad_lines="skip")
        return read_cordis_csv(os.path.join(d, name + ".csv"), first_n)
    if os.path.exists(os.path.join(d, name + ".xlsx")):
        return pd.read_excel(os.path.join(d, name + ".xlsx"), dtype=str)
    raise SystemExit(f"Fichier manquant : {d}/{name}.csv")


if __name__ == "__main__":
    os.makedirs(CACHE, exist_ok=True)
    print("CORDIS Horizon Europe")
    load("horizon", "organization").to_pickle(f"{CACHE}/organization.pkl")
    load("horizon", "project", first_n=14).to_pickle(f"{CACHE}/project.pkl")
    load("horizon", "euroSciVoc").to_pickle(f"{CACHE}/euroSciVoc.pkl")
    print("CORDIS H2020")
    load("h2020", "organization").to_pickle(f"{CACHE}/h2020_organization.pkl")
    load("h2020", "project", first_n=14).to_pickle(f"{CACHE}/h2020_project.pkl")
    print("ARAMIS")
    ar = pd.read_csv(os.path.join(RAW, "aramis_full_export.csv"), encoding="utf-8-sig", dtype=str)
    print(f"  {len(ar)} projets")
    ar.to_pickle(f"{CACHE}/aramis.pkl")
