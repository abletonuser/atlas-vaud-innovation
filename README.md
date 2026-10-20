# Atlas vaudois de l'innovation

Carte des projets d'innovation financés par l'Union européenne (H2020, Horizon Europe) et par Innosuisse, à trois échelles : organisations vaudoises, cantons suisses, pays européens. Uniquement des données publiques.

## Mise à jour automatique

Le flux `.github/workflows/update.yml` tourne le 4 de chaque mois (et à la demande, onglet *Actions*) :

1. `scripts/fetch_sources.py` télécharge CORDIS (H2020 et Horizon Europe), l'export ARAMIS et la population Eurostat.
2. `scripts/aramis_participants.py` lit les partenaires des **nouveaux** projets Innosuisse (service web public ARAMIS) et les ajoute à `data/state/innosuisse_participants.csv`.
3. `scripts/ide_sieges.py` retrouve le siège des nouvelles entreprises par leur numéro IDE (Zefix, données ouvertes LINDAS) dans `data/state/ide_sieges.csv`.
4. `scripts/build_all.sh` reconstruit la page autonome `dist/atlas-vaudois.html` et les contrôles `dist/controles.txt`.

La page publiée sur claude.ai est republiée chaque mois à partir de `dist/atlas-vaudois.html`.

## Sources

| Source | Mise à jour | Licence |
|---|---|---|
| CORDIS, projets H2020 et Horizon Europe | mensuelle | CC BY 4.0 |
| ARAMIS (SEFRI), projets Innosuisse et participants | continue | utilisation libre, source à citer |
| Zefix sur LINDAS (OFJ), sièges des entreprises | quotidienne | données ouvertes |
| Eurostat demo_r_pjanaggr3, population | annuelle | réutilisation libre |
| swiss-maps (OFS, swisstopo), world-atlas (Natural Earth), GeoNames | — | libres |

## Règles de calcul

- UE : comptée par participation, montant UE attribué exactement à chaque organisation.
- Innosuisse : comptée par projet ; un projet compte pour Vaud dès qu'un partenaire y est établi. Montant = coût total approuvé, compté une fois.
- Euros et francs ne sont jamais additionnés ni convertis.
- Aucune donnée personnelle (noms, e-mails, téléphones) n'est collectée.

## Collecte initiale sur un poste Windows

`tools/windows/aramis_participants.ps1` et `tools/windows/ide_sieges.ps1` font la même collecte sans installation (PowerShell). Leurs fichiers résultats se placent dans `data/state/`.

## Construire localement

```sh
pip install -r requirements.txt && npm ci
python scripts/fetch_sources.py .
sh scripts/build_all.sh
```
