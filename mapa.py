# Lê o KMZ das usinas (exportado do Google Earth) e devolve pontos e áreas para o mapa do Centro de Operações.
import re, sys, zipfile
import xml.etree.ElementTree as ET


def _categoria(pastas):
    p = " / ".join(pastas).lower()
    if "técnico" in p or "tecnico" in p:
        return "tecnico"
    if "base" in p:
        return "base"
    if "cluster" in p:
        return "cluster"
    return "usina"


def ler_kmz(caminho):
    with zipfile.ZipFile(caminho) as z:
        nome_kml = next(n for n in z.namelist() if n.lower().endswith(".kml"))
        raiz = ET.fromstring(z.read(nome_kml))
    ns = raiz.tag.split("}")[0] + "}" if raiz.tag.startswith("{") else ""
    pontos, areas = [], []

    def texto(e, tag):
        x = e.find(ns + tag)
        return (x.text or "").strip() if x is not None and x.text else ""

    def coords(s):
        out = []
        for trio in s.split():
            partes = trio.split(",")
            if len(partes) >= 2:
                try:
                    out.append([round(float(partes[1]), 6), round(float(partes[0]), 6)])  # [lat, lon]
                except ValueError:
                    pass
        return out

    def andar(e, pastas):
        for c in e:
            t = c.tag.replace(ns, "")
            if t in ("Folder", "Document"):
                andar(c, pastas + [texto(c, "name")])
            elif t == "Placemark":
                nome = texto(c, "name")
                desc = re.sub(r"<[^>]+>", " ", texto(c, "description"))
                desc = " ".join(desc.split())[:300]
                # tira o nome do arquivo e a pasta raiz ("Usinas Gerar.kmz / Usinas Gerar")
                uteis = [p for p in pastas if p and not p.lower().endswith(".kmz")][1:]
                cat = _categoria(uteis)
                grupo = uteis[-1] if uteis else ""
                pt = c.find(".//" + ns + "Point/" + ns + "coordinates")
                if pt is not None and pt.text:
                    xy = coords(pt.text)
                    if xy:
                        pontos.append({"nome": nome, "categoria": cat, "grupo": grupo,
                                       "pasta": " / ".join(uteis), "lat": xy[0][0], "lon": xy[0][1], "desc": desc})
                for anel in c.iter(ns + "Polygon"):
                    co = anel.find(".//" + ns + "outerBoundaryIs//" + ns + "coordinates")
                    if co is not None and co.text:
                        areas.append({"nome": nome, "categoria": cat, "grupo": grupo, "pontos": coords(co.text)})

    andar(raiz, [])
    return {"pontos": pontos, "areas": areas}


if __name__ == "__main__":
    d = ler_kmz(sys.argv[1])
    import collections
    print(len(d["pontos"]), "pontos,", len(d["areas"]), "áreas")
    print(collections.Counter((p["categoria"], p["grupo"]) for p in d["pontos"]).most_common(40))
    for cat in ("tecnico", "base", "usina"):
        print(cat, [p["nome"] for p in d["pontos"] if p["categoria"] == cat][:15])
