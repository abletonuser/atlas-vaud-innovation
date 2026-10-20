// Fonds de carte compacts pour la page : communes vaudoises, lacs, cantons suisses, pays du monde.
import fs from "fs";
import { feature } from "topojson-client";
import { topology } from "topojson-server";
import { presimplify, simplify, quantile } from "topojson-simplify";
import countries from "i18n-iso-countries";
import fr from "i18n-iso-countries/langs/fr.json" with { type: "json" };
countries.registerLocale(fr);
const ch = JSON.parse(fs.readFileSync("node_modules/swiss-maps/2026/ch-combined.json"));
const vdIds = new Set(Object.keys(JSON.parse(fs.readFileSync("data/ref/vd_commune_district.json"))).map(Number));
const muni = feature(ch, ch.objects.municipalities);
const vd = { type: "FeatureCollection", features: muni.features.filter(f => vdIds.has(+f.id)) };
const lakes = feature(ch, ch.objects.lakes);
const cantons = feature(ch, ch.objects.cantons);
function pack(objs, q) {
  let t = topology(objs, 1e5); t = presimplify(t); t = simplify(t, quantile(t, q)); return t;
}
const vdTopo = pack({ communes: vd, lakes }, 0.25);
const chTopo = pack({ cantons, lakes }, 0.2);
const world = JSON.parse(fs.readFileSync("node_modules/world-atlas/countries-110m.json"));
const iso = {};
for (const a2 of Object.keys(countries.getAlpha2Codes())) iso[a2] = { num: countries.alpha2ToNumeric(a2), fr: countries.getName(a2, "fr") };
fs.writeFileSync("build/geo.json", JSON.stringify({ vd: vdTopo, ch: chTopo, world, iso }));
console.log("geo.json", (fs.statSync("build/geo.json").size / 1024).toFixed(0), "Ko");
