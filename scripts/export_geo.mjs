import fs from "fs";
import { feature } from "topojson-client";
const t = JSON.parse(fs.readFileSync("node_modules/swiss-maps/2026/ch-combined.json"));
const muni = feature(t, t.objects.municipalities);
const cant = feature(t, t.objects.cantons);
fs.writeFileSync("build/ch_municipalities.geojson", JSON.stringify(muni));
fs.writeFileSync("build/ch_cantons.geojson", JSON.stringify(cant));
console.log(muni.features.length, cant.features.length, muni.features[0].id, cant.features.map(f=>f.id).join(","));
