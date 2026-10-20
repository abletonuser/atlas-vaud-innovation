import sys
tpl, data, geo, out = sys.argv[1:5]
def safe(p): return open(p, encoding="utf-8").read().replace("</", "<\\/")
html = open(tpl, encoding="utf-8").read().replace("__DATA__", safe(data)).replace("__GEO__", safe(geo))
open(out, "w", encoding="utf-8").write(html); print(out, round(len(html.encode())/1024), "Ko")
