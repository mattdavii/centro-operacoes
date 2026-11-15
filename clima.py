# Tempo nas usinas: previsão/observação por hora do Open-Meteo (grátis, sem chave) e avisos meteorológicos
# ativos do INMET. Serve para interpretar as ocorrências ("desarmou durante trovoada") e avisar antes.
# Só saem do PC as coordenadas das usinas, arredondadas a 0,1° (~10 km): nenhum nome, código ou mensagem.
import json, math, os, threading, time, urllib.parse, urllib.request

import config

ARQ = os.path.join(config.DADOS, "clima.json")
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
HISTORICO = "https://historical-forecast-api.open-meteo.com/v1/forecast"
GEOCODIFICAR = "https://geocoding-api.open-meteo.com/v1/search"
UFS = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
       "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
       "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
       "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
       "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}
_apelidos = {}    # cidade usada para um código fora do KMZ: {"cidade:Coroados": {"CAD200"}}
_pendentes = {}   # usina fora do KMZ esperando a coordenada da cidade: {chave: (cidade, uf)}
INMET = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
VALIDADE = 15 * 60          # atualiza a cada 15 min
CAMPOS = "temperature_2m,precipitation,weather_code,wind_gusts_10m,cloud_cover,shortwave_radiation"
_trava = threading.Lock()
_cache = {"dados": None}

# códigos WMO do Open-Meteo
TEMPO = {0: ("☀️", "céu limpo"), 1: ("🌤️", "poucas nuvens"), 2: ("⛅", "parcialmente nublado"), 3: ("☁️", "nublado"),
         45: ("🌫️", "neblina"), 48: ("🌫️", "neblina"), 51: ("🌦️", "garoa"), 53: ("🌦️", "garoa"), 55: ("🌦️", "garoa forte"),
         56: ("🌧️", "garoa congelante"), 57: ("🌧️", "garoa congelante"), 61: ("🌧️", "chuva fraca"), 63: ("🌧️", "chuva"),
         65: ("🌧️", "chuva forte"), 66: ("🌧️", "chuva congelante"), 67: ("🌧️", "chuva congelante"),
         80: ("🌦️", "pancadas"), 81: ("🌧️", "pancadas fortes"), 82: ("⛈️", "pancadas violentas"),
         95: ("⛈️", "trovoada"), 96: ("⛈️", "trovoada com granizo"), 99: ("⛈️", "trovoada com granizo")}


def chave_codigo(c):
    """CAR101 e CAR100 → CAR1 (mesma regra do mapa)."""
    import re
    m = re.match(r"^([A-Z]{2,4})(\d)\d*$", str(c or "").split("/")[0].strip().upper())  # "CAC100 (Blackout)" não é código
    return m.group(1) + m.group(2) if m else None


def _local(lat, lon):
    return f"{round(lat, 1):.1f},{round(lon, 1):.1f}"


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "centro-operacoes"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _ler():
    if _cache["dados"] is None:
        try:
            with open(ARQ, encoding="utf-8") as f:
                _cache["dados"] = json.load(f)
        except (OSError, ValueError):
            _cache["dados"] = {}
    return _cache["dados"]


def _gravar(d):
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, ARQ)
    _cache["dados"] = d


def _dentro(lat, lon, geo):
    """Ponto dentro do Polygon/MultiPolygon GeoJSON (coordenadas [lon, lat])."""
    polis = geo.get("coordinates") or []
    if geo.get("type") == "Polygon":
        polis = [polis]
    for poli in polis:
        if not poli:
            continue
        anel, dentro = poli[0], False
        j = len(anel) - 1
        for i in range(len(anel)):
            xi, yi = anel[i][0], anel[i][1]
            xj, yj = anel[j][0], anel[j][1]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
                dentro = not dentro
            j = i
        if dentro:
            return True
    return False


def _avisos(pontos):
    """Avisos do INMET (hoje e próximos), com as usinas que estão dentro da área de cada um."""
    bruto = _get(INMET, timeout=40)
    saida = []
    for quando in ("hoje", "futuro"):
        for a in bruto.get(quando) or []:
            if str(a.get("encerrado")).lower() == "true":
                continue
            try:
                geo = json.loads(a.get("poligono") or "{}")
            except ValueError:
                continue
            dentro = sorted({p["codigo"] for p in pontos if _dentro(p["lat"], p["lon"], geo)})
            if not dentro:
                continue
            saida.append({"id": a.get("id"), "descricao": a.get("descricao"), "severidade": a.get("severidade"),
                          "cor": a.get("aviso_cor"), "inicio": a.get("inicio"), "fim": a.get("fim"),
                          "quando": quando, "riscos": str(a.get("riscos") or "").strip("[]'\"")[:400],
                          "usinas": dentro, "geo": geo})
    return saida


def atualizar(pontos, forcar=False):
    """pontos: [{"codigo","lat","lon"}] das usinas do KMZ. Busca o tempo (se passou da validade) e grava."""
    if not pontos or not _trava.acquire(blocking=False):
        return
    try:
        d = _ler()
        if not forcar and time.time() - d.get("ts", 0) < VALIDADE and not _pendentes:
            return
        extras = dict(d.get("extras") or {})
        for chave, (cidade, uf) in list(_pendentes.items())[:20]:
            extras[chave] = _geocodificar(cidade, uf, pontos)
            _pendentes.pop(chave, None)
        pontos = pontos + [{"codigo": k, "lat": float(v.split(",")[0]), "lon": float(v.split(",")[1])}
                           for k, v in extras.items() if v]
        locais = sorted({_local(p["lat"], p["lon"]) for p in pontos})
        tempo, erro = {}, None
        for i in range(0, len(locais), 50):
            lote = locais[i:i + 50]
            q = urllib.parse.urlencode({
                "latitude": ",".join(l.split(",")[0] for l in lote), "longitude": ",".join(l.split(",")[1] for l in lote),
                "hourly": CAMPOS, "current": CAMPOS, "past_days": 3, "forecast_days": 2,
                "timezone": "America/Sao_Paulo", "timeformat": "unixtime"})
            try:
                r = _get(OPEN_METEO + "?" + q)
                for l, x in zip(lote, r if isinstance(r, list) else [r]):
                    tempo[l] = {"atual": x.get("current"), "hora": x.get("hourly")}
            except Exception as e:
                erro = f"Open-Meteo: {e}"
        try:
            avisos = _avisos(pontos)
        except Exception as e:
            avisos, erro = d.get("avisos", []), f"INMET: {e}"
        _gravar({"ts": time.time() if tempo else d.get("ts", 0), "tempo": tempo or d.get("tempo", {}),
                 "avisos": avisos, "erro": erro, "historico": _ler().get("historico") or {}, "extras": extras,
                 "usinas": {p["codigo"]: _local(p["lat"], p["lon"]) for p in pontos}})
        try:
            import relatorio  # completa o tempo das ocorrências antigas, aos poucos
            preencher_historico(list(relatorio._ler(relatorio.HIST, {}).values()))
        except Exception as e:
            print("clima: histórico:", e, flush=True)
    finally:
        _trava.release()


def atualizar_em_segundo_plano(pontos):
    if time.time() - _ler().get("ts", 0) >= VALIDADE or _pendentes:
        threading.Thread(target=atualizar, args=(pontos,), daemon=True).start()


def _geocodificar(cidade, uf, pontos):
    """Coordenada da cidade (Open-Meteo, só o nome da cidade sai do PC). Sem UF, aceita só a cidade mais perto
    das usinas do KMZ (evita o homônimo do outro lado do país). None se não achar."""
    try:
        r = _get(GEOCODIFICAR + "?" + urllib.parse.urlencode({"name": cidade, "count": 10, "language": "pt", "countryCode": "BR"}))
    except Exception:
        return None
    res = [x for x in r.get("results") or [] if x.get("feature_code", "").startswith("PPL")]
    if uf:
        res = [x for x in res if x.get("admin1") == UFS.get(uf)]
    elif pontos:
        # sem UF: só cidades a menos de ~150 km de alguma usina do KMZ; entre elas, a maior
        perto = lambda x: min(math.hypot(x["latitude"] - p["lat"], x["longitude"] - p["lon"]) for p in pontos)
        res = [x for x in res if perto(x) <= 1.4]
    if not res:
        return None
    x = max(res, key=lambda x: x.get("population") or 0)
    return _local(x["latitude"], x["longitude"])


def cidade_de(o):
    """('Coroados', 'SP') a partir do nome da usina: "CAD200 – Coroados 200", "UFV Mucugê-BA", "UFV Santa Adélia - SP"."""
    import re
    if o.get("generico"):
        return None, None  # grupo geral sem usina identificada
    nome = re.sub(r"\s+Gerar\s*$", "", str(o.get("usina") or ""))
    m = re.search(r"[-–/\s]\s*([A-Z]{2})\s*$", nome)
    uf = m.group(1) if m and m.group(1) in UFS else None
    if uf:
        nome = nome[:m.start()]
    nome = re.sub(r"\([^)]*\)|\bUFVs?\b|\b[A-Z]{2,4}\d{3}(?:/\d{3})?\b|[–—]|\b\d+\b|\b(I{1,3}|IV|V|VI)\b|\bGerar\b", " ", nome)
    nome = " ".join(w for w in nome.replace("-", " ").replace(",", " ").split() if w != "e").strip(" .,")
    return (nome, uf) if len(nome) >= 3 else (None, None)


def chave_local(o):
    """Por onde buscar o tempo da ocorrência: o código do KMZ ou, se a usina não está lá, a cidade."""
    cod = o.get("codigo")
    if cod and _local_da_usina(cod):
        return cod
    cidade, uf = cidade_de(o)
    if cod and not cidade:
        # só o código ("UFV CAD100/CAD200"): usa o nome aprendido do COG para o código, ou de outro da mesma sigla
        import re, relatorio
        nomes = relatorio.codigos()
        sigla = re.match(r"[A-Z]+", str(cod)).group(0) if re.match(r"[A-Z]+", str(cod)) else None
        nome = nomes.get(str(cod).split("/")[0]) or next((n for c, n in nomes.items() if sigla and c.startswith(sigla)), None)
        if nome:
            cidade, uf = cidade_de({"usina": nome})
    if not cidade:
        return None
    chave = "cidade:" + cidade + ("|" + uf if uf else "")
    extras = _ler().get("extras") or {}
    if chave not in extras:
        _pendentes[chave] = (cidade, uf)
        return None
    if cod and extras[chave]:
        _apelidos.setdefault(chave, set()).update(x.strip() for x in str(cod).split("/"))
    return chave if extras[chave] else None


def _local_da_usina(codigo):
    d = _ler()
    if str(codigo).startswith("cidade:"):
        return (d.get("extras") or {}).get(codigo)
    us = d.get("usinas") or {}
    if codigo in us:
        return us[codigo]
    k = chave_codigo(codigo)
    achado = next((l for c, l in us.items() if chave_codigo(c) == k), None) if k else None
    if achado or not k:
        return achado
    # outra unidade da mesma usina (CAC200 quando o KMZ só tem CAC100): vale se a sigla tem um ponto só
    import re
    sigla = re.match(r"[A-Z]+", k).group(0)
    mesmos = {l for c, l in us.items() if re.fullmatch(sigla + r"\d{3}", c)}
    return mesmos.pop() if len(mesmos) == 1 else None


def nivel(precip, rajada, cod):
    """'severo' (trovoada, chuva forte, vendaval), 'chuva' (chuva/vento moderados) ou None."""
    if (cod or 0) >= 95 or (precip or 0) >= 10 or (rajada or 0) >= 60 or cod in (65, 82):
        return "severo"
    if (precip or 0) >= 1 or (rajada or 0) >= 50 or (cod or 0) >= 55:
        return "chuva"  # garoa fraca e vento comum não contam; garoa forte (molha equipamento, baixa R.I) conta
    return None


def rotulo(c):
    em, nome = TEMPO.get(c.get("codigo"), ("🌡️", "—"))
    partes = [f"{em} {nome}"]
    if c.get("chuva"):
        partes.append(f"{c['chuva']:.0f} mm/h" if c["chuva"] >= 1 else f"{c['chuva']:.1f} mm/h".replace(".", ","))
    if c.get("rajada") and c["rajada"] >= 30:
        partes.append(f"rajada {c['rajada']:.0f} km/h")
    if c.get("temp") is not None:
        partes.append(f"{c['temp']:.0f}°C")
    return " · ".join(partes)


def tempo_em(codigo, ts, margem=3600, serie=None):
    """O tempo na usina por volta de ts (pior hora entre ts-1h e ts+1h): chuva e rajada máximas,
    trovoada se houve. None se não há dado (usina sem coordenada ou ts fora dos 3 dias guardados)."""
    loc = _local_da_usina(codigo)
    h = serie or (((_ler().get("tempo") or {}).get(loc) or {}).get("hora") if loc else None)
    if not h or not h.get("time"):
        return None
    idx = [i for i, t in enumerate(h["time"]) if ts - margem - 3600 < t <= ts + margem]
    if not idx:
        return None
    pega = lambda campo: [h[campo][i] for i in idx if h.get(campo) and h[campo][i] is not None]
    chuva, rajada, cods = max(pega("precipitation") or [0]), max(pega("wind_gusts_10m") or [0]), pega("weather_code")
    cod = max(cods, key=lambda c: (c >= 95, c >= 80, c >= 61, c)) if cods else None
    perto = min(idx, key=lambda i: abs(h["time"][i] - ts))
    c = {"codigo": cod, "chuva": round(chuva, 1), "rajada": round(rajada), "temp": (h.get("temperature_2m") or [None])[perto],
         "nuvens": (h.get("cloud_cover") or [None])[perto], "irradiacao": (h.get("shortwave_radiation") or [None])[perto],
         "ts": ts}
    c["nivel"] = nivel(chuva, rajada, cod)
    c["rotulo"] = rotulo(c)
    return c


def _em_vigor(a, agora=None):
    agora = agora or time.time()
    try:
        ini = time.mktime(time.strptime(a["inicio"], "%Y-%m-%d %H:%M"))
        fim = time.mktime(time.strptime(a["fim"], "%Y-%m-%d %H:%M"))
    except (KeyError, TypeError, ValueError):
        return a.get("quando") == "hoje"
    return ini <= agora <= fim + 60


def _codigo_no_kmz(codigo):
    """O código do KMZ que dá a posição da usina (CAC200 → CAC100 quando o KMZ só tem o 100)."""
    us = _ler().get("usinas") or {}
    loc = _local_da_usina(codigo)
    if not loc or any(chave_codigo(c) == chave_codigo(codigo) for c in us):
        return codigo
    return next((c for c, l in us.items() if l == loc and str(c)[:3] == str(codigo)[:3]), codigo)


def avisos_da_usina(codigo):
    """Avisos do INMET em vigor agora sobre a usina (um por tipo: o mais severo)."""
    if not str(codigo).startswith("cidade:"):
        codigo = _codigo_no_kmz(codigo)
    k = codigo if str(codigo).startswith("cidade:") else chave_codigo(codigo)
    por_tipo = {}
    for a in _ler().get("avisos") or []:
        if _em_vigor(a) and any((u if u.startswith("cidade:") else chave_codigo(u)) == k for u in a["usinas"]):
            atual = por_tipo.get(a["descricao"])
            if not atual or GRAVIDADE.get(a["severidade"], 0) > GRAVIDADE.get(atual["severidade"], 0):
                por_tipo[a["descricao"]] = a
    return list(por_tipo.values())


GRAVIDADE = {"Perigo Potencial": 1, "Perigo": 2, "Grande Perigo": 3}


def de(o):
    """O tempo anotado na ocorrência, ou o preenchido depois para o histórico."""
    return o.get("clima") or (_ler().get("historico") or {}).get(o.get("chave"))


def preencher_historico(ocorrencias, limite=40):
    """Ocorrências antigas (do histórico) sem tempo anotado: busca a série por hora da época no arquivo
    histórico do Open-Meteo e guarda em clima.json["historico"][chave]. Poucas consultas por vez."""
    d = _ler()
    feito = d.get("historico") or {}
    falta = [o for o in ocorrencias if o.get("chave") not in feito and not o.get("clima")
             and time.time() - o["inicio_ts"] > 2 * 86400 and chave_local(o)]
    if not falta:
        return 0
    por_local = {}
    for o in falta:
        por_local.setdefault(_local_da_usina(chave_local(o)), []).append(o)
    n = 0
    for loc, ocs in list(por_local.items())[:limite]:
        ini = time.strftime("%Y-%m-%d", time.localtime(min(o["inicio_ts"] for o in ocs) - 86400))
        fim = time.strftime("%Y-%m-%d", time.localtime(max(o["inicio_ts"] for o in ocs) + 86400))
        lat, lon = loc.split(",")
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "hourly": CAMPOS, "start_date": ini, "end_date": fim,
                                    "timezone": "America/Sao_Paulo", "timeformat": "unixtime"})
        try:
            h = _get(HISTORICO + "?" + q).get("hourly")
        except Exception:
            continue
        for o in ocs:
            c = tempo_em(chave_local(o), o["inicio_ts"], serie=h)
            feito[o["chave"]] = c or {}
            n += 1
    d = dict(_ler(), historico=feito)
    _gravar(d)
    return n


def anotar(ocorrencias):
    """Acrescenta o tempo na hora do início de cada ocorrência (e o aviso do INMET em vigor, se houver).
    O que já foi anotado fica (o histórico guarda; o dado por hora só cobre 3 dias)."""
    for o in ocorrencias:
        cod = chave_local(o)
        if not cod:
            continue
        if not o.get("clima"):
            c = tempo_em(cod, o["inicio_ts"]) or (_ler().get("historico") or {}).get(o.get("chave"))
            if c:
                o["clima"] = c
        if not o.get("normalizado"):
            agora = time.time()
            o["clima_agora"] = tempo_em(cod, agora, margem=0)  # a última hora medida
            # pior hora das próximas 6 h (para decidir quando mandar o técnico)
            prev = tempo_em(cod, agora + 3 * 3600 + 1800, margem=3 * 3600)
            if prev and prev.get("nivel"):
                h = (((_ler().get("tempo") or {}).get(_local_da_usina(cod)) or {}).get("hora") or {})
                pior = [t for t, p, g, c in zip(h.get("time", []), h.get("precipitation", []), h.get("wind_gusts_10m", []),
                                                h.get("weather_code", []))
                        if agora < t <= agora + 6 * 3600 and nivel(p, g, c)]
                prev["quando"] = pior[0] if pior else None
                o["clima_previsao"] = prev
            else:
                o["clima_previsao"] = None
            av = avisos_da_usina(cod)
            o["aviso_inmet"] = [{"descricao": a["descricao"], "severidade": a["severidade"], "cor": a["cor"],
                                 "fim": a["fim"]} for a in av] or None


def resumo():
    """Para o painel: avisos ativos (sem o polígono) e quando foi atualizado."""
    d = _ler()
    return {"ts": d.get("ts"), "erro": d.get("erro"),
            "avisos": [{k: v for k, v in a.items() if k != "geo"} for a in d.get("avisos") or []]}


def mapa():
    """Tempo atual por usina e avisos com polígono (camada do mapa)."""
    d = _ler()
    atual = {}
    for cod, loc in (d.get("usinas") or {}).items():
        a = ((d.get("tempo") or {}).get(loc) or {}).get("atual")
        if a:
            c = {"codigo": a.get("weather_code"), "chuva": a.get("precipitation") or 0, "rajada": a.get("wind_gusts_10m") or 0,
                 "temp": a.get("temperature_2m"), "nuvens": a.get("cloud_cover"), "irradiacao": a.get("shortwave_radiation")}
            c["nivel"] = nivel(c["chuva"], c["rajada"], c["codigo"])
            c["rotulo"] = rotulo(c)
            atual[cod] = c
    return {"ts": d.get("ts"), "atual": atual, "avisos": d.get("avisos") or []}


def _pior(h, t0, t1):
    """Pior hora da série entre t0 e t1 (trovoada > chuva forte > rajada), com o horário. None se tempo bom."""
    melhor = None
    for i, t in enumerate(h.get("time") or []):
        if not (t0 < t <= t1):
            continue
        p, g, c = (h.get("precipitation") or [0])[i] or 0, (h.get("wind_gusts_10m") or [0])[i] or 0, (h.get("weather_code") or [0])[i] or 0
        n = nivel(p, g, c)
        if not n:
            continue
        peso = (n == "severo", c >= 95, p, g)
        if not melhor or peso > melhor[0]:
            x = {"codigo": c, "chuva": round(p, 1), "rajada": round(g), "temp": (h.get("temperature_2m") or [None])[i], "quando": t, "nivel": n}
            x["rotulo"] = rotulo(x)
            melhor = (peso, x)
    return melhor[1] if melhor else None


def painel():
    """Aba CLIMA: avisos do INMET (hoje e próximos) e, por local, o tempo agora e o pior das próximas 6 h e 24 h."""
    d = _ler()
    try:
        import relatorio
        nomes = relatorio.codigos()
    except Exception:
        nomes = {}
    por_local = {}
    for cod, loc in sorted((d.get("usinas") or {}).items()):
        por_local.setdefault(loc, []).append(cod)
    for chave, loc in (d.get("extras") or {}).items():
        if loc:
            por_local.setdefault(loc, []).extend(sorted(_apelidos.get(chave, ())) or [chave])
    agora = time.time()
    usinas = []
    for loc, cods in por_local.items():
        t = (d.get("tempo") or {}).get(loc) or {}
        h = t.get("hora") or {}
        a = t.get("atual") or {}
        atual = None
        if a:
            atual = {"codigo": a.get("weather_code"), "chuva": a.get("precipitation") or 0, "rajada": round(a.get("wind_gusts_10m") or 0),
                     "temp": a.get("temperature_2m"), "nuvens": a.get("cloud_cover")}
            atual["nivel"] = nivel(atual["chuva"], atual["rajada"], atual["codigo"])
            atual["rotulo"] = rotulo(atual)
        p6, p24 = _pior(h, agora, agora + 6 * 3600), _pior(h, agora, agora + 24 * 3600)
        so_codigos = [c for c in cods if not c.startswith("cidade:")]
        rot = so_codigos or list(dict.fromkeys("📍 " + c[7:].split("|")[0] for c in cods))
        nome = next((nomes.get(c) for c in cods if nomes.get(c)), None)
        avisos = sorted({a2["descricao"] for a2 in d.get("avisos") or [] if _em_vigor(a2) and set(a2["usinas"]) & set(cods)})
        usinas.append({"codigos": cods, "rotulo": " · ".join(rot[:4]) + (f" +{len(rot) - 4}" if len(rot) > 4 else ""), "nome": nome,
                       "local": loc, "atual": atual, "prox6": p6, "prox24": p24, "avisos": avisos})
    avisos = sorted([dict({k: v for k, v in a.items() if k != "geo"}, em_vigor=_em_vigor(a)) for a in d.get("avisos") or []],
                    key=lambda a: (not a["em_vigor"], a.get("inicio") or "", -GRAVIDADE.get(a.get("severidade"), 0)))
    return {"ts": d.get("ts"), "proxima": (d.get("ts") or agora) + VALIDADE, "erro": d.get("erro"), "avisos": avisos, "usinas": usinas}


if __name__ == "__main__":
    import sys, mapa as m
    pts = [{"codigo": p["nome"], "lat": p["lat"], "lon": p["lon"]}
           for p in m.ler_kmz(config.kmz())["pontos"] if p["categoria"] == "usina"]
    atualizar(pts, forcar=True)
    d = _ler()
    print(len(d.get("tempo", {})), "locais;", len(d.get("avisos", [])), "avisos;", "erro:", d.get("erro"))
    for a in d.get("avisos", []):
        print(" ", a["quando"], a["descricao"], a["severidade"], a["inicio"], "→", a["fim"], len(a["usinas"]), "usinas:", a["usinas"][:8])
    for cod in sys.argv[1:]:
        print(cod, tempo_em(cod, time.time()))
