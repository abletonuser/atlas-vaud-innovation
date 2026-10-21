"""Collecte incrémentale des participants des projets Innosuisse publiés dans ARAMIS.

1. Liste des projets : pages publiques https://datenausgabe.aramis.admin.ch/projects, filtrées sur Innosuisse,
   triées par date de début décroissante, jusqu'à l'année --depuis.
2. Participants : service web public ARAMIS (/project/?aramisId=…), à défaut page publique « Beteiligte ».
   Seuls les projets absents de data/state/innosuisse_participants.csv sont lus (mise à jour incrémentale).

Aucun nom de personne, e-mail ou téléphone n'est conservé : organisation, numéro IDE, NPA, localité, rôle.
Usage : python scripts/aramis_participants.py [--depuis 2018] [--pause 0.6] [--max N] [--test]
"""
import argparse, csv, html, json, os, re, sys, time
import requests

LIST_URL = "https://datenausgabe.aramis.admin.ch/projects"
PAGE_URL = "https://www.aramis.admin.ch/Beteiligte/?ProjectID={0}&Sprache=de-CH"
WS_URLS = ["https://www.webservice.aramis.admin.ch/public/service.svc/project/?aramisId={0}&Language=FR",
           "https://www.webservice.aramis.admin.ch/Public/Service.svc/project/?aramisId={0}&Language=FR"]
INNO_NUM = re.compile(r"\s(IP|INNO|INT)-[A-Z]+\s*$")
UID_RE = re.compile(r"CHE-?(\d{3})\.?(\d{3})\.?(\d{3})")
FIELDS = ["ProjectNumber", "AramisId", "KindOfParticipation", "Type", "UID", "Company", "PostCode", "City", "Canton", "Country"]
S = requests.Session()
S.headers["User-Agent"] = "atlas-vaud-innovation/1.0 (collecte ponctuelle, cadence lente)"


def get_text(url, accept="text/html"):
    for attempt in range(3):
        try:
            r = S.get(url, headers={"Accept": accept}, timeout=60)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text.lstrip("﻿")
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def strip(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def uid_of(text):
    m = UID_RE.search(text or "")
    return "CHE" + "".join(m.groups()) if m else ""


def join_parts(vals):
    """Les champs ARAMIS sont coupés à 35 caractères : recolle sans espace quand la suite commence par une minuscule."""
    r = ""
    for x in vals:
        if not x:
            continue
        x = re.sub(r"\s+", " ", x).strip()
        r = r + x if r and re.match(r"[a-zàâçéèêëîïôûù]", x) else (r + " " + x).strip()
    return r


# ---------- 1. Liste ----------
def parse_list_page(h):
    rows = []
    for tr in re.findall(r"(?is)<tr\b.*?</tr>", h):
        m = re.search(r"ProjectID=(\d+)", tr)
        if not m:
            continue
        cells = [strip(c) for c in re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", tr)]
        num = next((c for c in cells if INNO_NUM.search(c)), cells[0] if cells else "")
        txt = strip(tr)
        years = [int(y) for y in re.findall(r"\b\d{2}\.\d{2}\.(\d{4})\b", txt)]
        rows.append({"Id": m.group(1), "ProjectNumber": num, "Office": txt, "Year": years[0] if years else None})
    return rows


def get_list(params):
    for attempt in range(3):
        try:
            r = S.get(LIST_URL, params=params, timeout=60); r.raise_for_status(); r.encoding = "utf-8"
            return r.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def last_page(h):
    return max([int(x) for x in re.findall(r"page=(\d+)", h)] + [1])


def list_projects(depuis, pause, test):
    """Liste des projets Innosuisse. Tri par identifiant interne (clé unique) : le tri par date de début, plein
    d'ex aequo, rend la pagination instable (environ 8 % de projets sautés ou lus deux fois, vérifié en octobre 2026)."""
    first = get_text(LIST_URL)
    filt = []
    for name, body in re.findall(r'(?is)<select\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</select>', first):
        for val, label in re.findall(r'(?is)<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)</option>', body):
            lab = strip(label)
            if "INNOSUISSE" in lab and "EVAL" not in lab and val:
                filt = [(html.unescape(name), html.unescape(val))]
    base = [("q[s]", "id desc")]
    p1 = get_list(base + filt + [("page", 1)]); rows = parse_list_page(p1)
    if filt and rows and sum("INNOSUISSE" in r["Office"] for r in rows) / len(rows) < 0.8:
        print("  filtre Innosuisse ignoré (non appliqué par le site)")
        filt = []; p1 = get_list(base + [("page", 1)]); rows = parse_list_page(p1)
    if not rows:
        raise SystemExit("Aucun projet reconnu sur la page de liste ARAMIS : structure du site modifiée ?")
    # filtre sur la date de début, gardé seulement s'il réduit vraiment la liste
    for fmt in (f"{depuis}-01-01", f"01.01.{depuis}"):
        extra = [("q[start_date_gteq]", fmt)]
        t = get_list(base + filt + extra + [("page", 1)]); r2 = parse_list_page(t)
        if r2 and last_page(t) < last_page(p1) and all(r["Year"] is None or r["Year"] >= depuis for r in r2):
            base += extra; p1, rows = t, r2
            print(f"  filtre de date actif ({fmt})"); break
    last = last_page(p1)
    print(f"  {last} pages à lire")
    out, seen, nrows, page = [], set(), 0, 1
    while True:
        nrows += len(rows)
        for r in rows:
            inno = INNO_NUM.search(r["ProjectNumber"] or "") or ("INNOSUISSE" in r["Office"] and "EVAL" not in r["Office"])
            if inno and (r["Year"] is None or r["Year"] >= depuis) and r["Id"] not in seen:
                seen.add(r["Id"]); out.append(r)
        if test or page >= last:
            break
        page += 1; time.sleep(pause)
        try:
            rows = parse_list_page(get_list(base + filt + [("page", page)]))
        except requests.RequestException as e:
            print(f"  page {page} : échec ({e}), on continue"); rows = []
        if page % 50 == 0:
            print(f"  page {page}/{last} : {len(out)} projets Innosuisse")
    print(f"  lignes lues {nrows}, projets distincts {len(seen)} (projets Innosuisse {depuis}+ : {len(out)})")
    return out


def controle_export(listed, depuis, path="data/raw/aramis_full_export.csv"):
    """Compare la liste lue à l'export officiel ARAMIS : signale les projets Innosuisse absents de la liste."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        exp = {r["Projektnummer"] for r in csv.DictReader(f)
               if r.get("Forschungsstelle") == "INNOSUISSE" and (r.get("Projektstart") or "")[:4].isdigit()
               and int(r["Projektstart"][:4]) >= depuis}
    got = {p["ProjectNumber"] for p in listed}
    miss = exp - got
    print(f"  contrôle : export ARAMIS {len(exp)} projets Innosuisse {depuis}+, absents de la liste {len(miss)}"
          + (f" (ex. {sorted(miss)[:5]})" if miss else ""))


# ---------- 2. Participants ----------
def flat(o, acc):
    """Aplati un objet JSON ARAMIS ; textes localisés {LanguageCode, Text} ramenés à leur texte (FR de préférence)."""
    if isinstance(o, list):
        for x in o:
            flat(x, acc)
        return
    if not isinstance(o, dict):
        return
    for k, v in o.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float)):
            acc.setdefault(k, str(v))
        elif isinstance(v, dict) and "Text" in v and "LanguageCode" in v:
            acc.setdefault(k, v["Text"] or "")
        elif isinstance(v, list) and v and isinstance(v[0], dict) and "LanguageCode" in v[0]:
            fr = next((x for x in v if x.get("LanguageCode") == "FR"), v[0])
            acc.setdefault(k, fr.get("Text") or "")
        else:
            flat(v, acc)


def first(acc, *keys):
    return next((acc[k] for k in keys if acc.get(k)), "")


def from_ws(pid):
    for u in WS_URLS:
        try:
            txt = get_text(u.format(pid), "application/json")
            o = json.loads(txt)
            o = o.get("d", o)
            parts = []
            for q in o.get("Participants") or []:
                acc = {}
                flat(q, acc)
                parts.append({"KindOfParticipation": first(acc, "KindOfParticipation", "Role"), "Type": first(acc, "Type"),
                              "UID": uid_of(" ".join(filter(None, [acc.get("URL1"), acc.get("URL2"), acc.get("ShortDesignation")]))),
                              "Company": join_parts([acc.get(f"Company{i}") for i in range(1, 5)]),
                              "PostCode": first(acc, "PostCode", "PostalCode", "ZipCode"), "City": first(acc, "City", "Place"),
                              "Canton": first(acc, "Canton"), "Country": first(acc, "Country")})
            if parts:
                return parts
        except (requests.RequestException, ValueError):
            continue
    return None


TITLE = re.compile(r"^(?:(?:Prof(?:essor|esseur)?|Dr|Doktor|Docteur|PD|Herr|Frau|Monsieur|Madame|Mme)\.?\s*)+$")
ORGKW = re.compile(r"(?i)\b(SA|AG|GmbH|S[aà]rl|Sagl|Ltd|Inc|SE|Stiftung|Fondation|Foundation|Verein|Association|Universit\w*|"
                   r"Hochschule|Fachhochschule|Haute|[EÉ]cole|School|Institut\w*|Center|Centre|Zentrum|EPFL|ETH|HES|ZHAW|FHNW|"
                   r"BFH|HSLU|OST|SUPSI|EMPA|Eawag|PSI|WSL|CSEM|Idiap|Spital|H[ôo]pital|Clinique|Klinik|CHUV)\b")


def from_page(pid):
    h = get_text(PAGE_URL.format(pid))
    out = []
    for tr in re.findall(r"(?is)<tr\b.*?</tr>", h):
        cells = re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", tr)
        if len(cells) < 2:
            continue
        role = strip(cells[0])
        if not role or len(role) > 40 or re.search(r"Bundesstelle|Verwaltungseinheit", role):
            continue
        raw = re.sub(r'(?i)<a\b[^>]*href="[^"]*?(CHE\d{9})[^"]*"[^>]*>.*?</a>', r"\n\1\n", cells[1])
        raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</span>", "\n", raw)
        lines = [re.sub(r"\s+", " ", l).strip() for l in html.unescape(re.sub(r"<[^>]+>", "", raw)).split("\n")]
        lines = [l for l in lines if l]
        if not lines:
            continue
        uid = uid_of(" ".join(lines))
        L = [l for l in lines if "@" not in l and not re.match(r"^(\+|0)\d[\d\s/().-]{6,}", l)
             and not re.match(r"^(https?://|www\.)", l) and not re.match(r"^CHE\d{9}$", l) and not TITLE.match(l)]
        npa = city = country = ""; iz = -1
        for k, l in enumerate(L):
            m = re.match(r"^([A-Z]{1,3})-\s?(\d{4,5})\s+(.+)$", l)
            if m:
                country, npa, city, iz = m.group(1), m.group(2), m.group(3), k
        before = L[:iz] if iz >= 0 else L
        if iz > 0 and before and re.search(r"\d|strasse|weg|rue|avenue|chemin|route|via|platz|place|station|postfach", before[-1], re.I) \
                and not ORGKW.search(before[-1]):
            before = before[:-1]
        if len(before) >= 2 and not ORGKW.search(before[0]):
            before = before[1:]                                   # nom de la personne
        company = join_parts(before)
        if company and not ORGKW.search(company) and re.fullmatch(r"[A-ZÀ-Ý][\w'-]+(\s[A-ZÀ-Ý][\w'-]+){1,2}", company):
            company = ""
        out.append({"KindOfParticipation": role, "Type": "", "UID": uid, "Company": company, "PostCode": npa,
                    "City": city, "Canton": "", "Country": country})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", type=int, default=2018); ap.add_argument("--pause", type=float, default=0.6)
    ap.add_argument("--max", type=int, default=0); ap.add_argument("--test", action="store_true")
    ap.add_argument("--state", default="data/state/innosuisse_participants.csv")
    ap.add_argument("--anciens-d-abord", action="store_true", help="lit les projets les plus anciens en premier (collecte en parallèle d'un poste qui lit les plus récents)")
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.state) and not a.test:
        with open(a.state, encoding="utf-8-sig") as f:
            done = {r["AramisId"] for r in csv.DictReader(f)}
    print(f"Projets déjà collectés : {len(done)}")
    listed = list_projects(a.depuis, min(a.pause, 0.3), a.test)
    if not a.test:
        controle_export(listed, a.depuis)
    projects = [p for p in listed if p["Id"] not in done]
    projects.sort(key=lambda p: p["Year"] or 0, reverse=not a.anciens_d_abord)
    if a.test:
        projects = projects[:3]
    elif a.max:
        projects = projects[:a.max]
    print(f"Nouveaux projets Innosuisse à lire : {len(projects)}")
    out_path = a.state if not a.test else "innosuisse_participants_test.csv"
    new_file = not os.path.exists(out_path) or a.test
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w" if new_file else "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        mode, ws_fail, t0 = "ws", 0, time.time()
        for i, p in enumerate(projects, 1):
            parts = from_ws(p["Id"]) if mode == "ws" else None
            if parts is None and mode == "ws":
                ws_fail += 1
                if ws_fail >= 3 and i <= 5:
                    mode = "page"; print("  service web indisponible : lecture des pages publiques")
            if parts is None:
                try:
                    parts = from_page(p["Id"])
                except requests.RequestException as e:
                    print(f"  {p['ProjectNumber']} : échec ({e})"); continue
            for q in parts:
                w.writerow({"ProjectNumber": p["ProjectNumber"], "AramisId": p["Id"], **{k: q.get(k, "") for k in FIELDS[2:]}})
            f.flush()
            if a.test:
                print(f"  {p['ProjectNumber']} -> " + " | ".join(f"{q['KindOfParticipation']}: {q['Company']} [{q['UID']}]" for q in parts))
            elif i % 50 == 0:
                print(f"  {i}/{len(projects)} projets lus, environ {int((len(projects) - i) * (time.time() - t0) / i / 60)} min restantes")
            time.sleep(a.pause)
    print(f"Terminé : {len(projects)} projets ajoutés à {out_path}")


if __name__ == "__main__":
    main()
