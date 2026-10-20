#!/bin/sh
# Reconstruit l'atlas à partir des sources téléchargées : tables, fonds de carte, données, page autonome.
set -e
cd "$(dirname "$0")/.."
mkdir -p build dist
python scripts/prepare.py .
node scripts/export_geo.mjs
node scripts/build_geo.mjs
python scripts/build_data.py .
python scripts/assemble.py web/template.html build/data.json build/geo.json dist/atlas-vaudois.html
cp build/qa.txt dist/controles.txt
