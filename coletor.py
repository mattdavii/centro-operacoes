#!/usr/bin/env python3
# Coletor do Centro de Operações: lê o WhatsApp pelo wa-app (só leitura) e, se configurado, o Diário de Chamados,
# e decide o que está esperando o usuário.
#   - privado: a última mensagem não é dele
#   - grupo: alguém marcou (@me) ou citou o nome dele (config.json: nome_usuario, apelidos) depois da última fala dele
# Pode ser rodado sozinho para depurar:  coletor.py [--dias 3]
import datetime as dt, json, os, re, subprocess, sys, time, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

DIAS = 3            # janela de conversas olhadas
POR_CHAT = 400      # mensagens lidas por conversa, no máximo
def citacao():
    """Regex de "citou seu nome": nome e apelidos do config.json (sem nome configurado, só vale o @)."""
    c = config.carregar()
    nomes = [n for n in [c.get("nome_usuario")] + list(c.get("apelidos") or []) if n and len(n.strip()) >= 3]
    if not nomes:
        return re.compile(r"(?!x)x")
    return re.compile(r"\b(" + "|".join(re.escape(sem_acento(n.strip())) for n in nomes) + r")\b", re.I)
FECHO = re.compile(r"(ok+|blz|beleza|show|top|tmj|valeu|vlw|obrigad[oa]|obg|perfeito|certo|combinado|fechado|"
                   r"boa|massa|joia|jóia|pois é|conta comigo|conta cmg|k{3,}|[\W_]*)", re.I)


def wa(*args, timeout=60):
    r = subprocess.run([config.wa_comando(), *args, "--json"], capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"wa {' '.join(args)}: {r.stderr.strip()[:200] or 'falhou'}")
    return json.loads(r.stdout)


def texto(m):
    tr = m.get("transcript")
    tr = tr.get("text", "") if isinstance(tr, dict) else tr
    t = m.get("text") or (f"[áudio] {tr}" if tr else "")
    if not t and m.get("media"):
        md = m["media"]
        t = f"[{md.get('kind', 'mídia') if isinstance(md, dict) else 'mídia'}]"
    return " ".join(str(t).split())


def compacta(m):
    return {"id": m.get("id"), "ts": m.get("ts"), "de": "você" if m.get("sender") == "me" else (m.get("sender") or "?"),
            "texto": texto(m)[:300]}


def status():
    try:
        st = wa("status", timeout=15)
        return {"conexao": st.get("connection"), "lacunas": len(st.get("gaps") or [])}
    except Exception as e:
        return {"conexao": None, "lacunas": None, "erro": str(e)}


def chats_ativos(dias=DIAS):
    desde = dt.datetime.now().astimezone() - dt.timedelta(days=dias)
    saida = []
    for c in wa("chats", "--limit", "500")["chats"]:
        if not c.get("lastMessage") or str(c.get("jid", "")).startswith("status@") or c.get("name") == "Status":
            continue
        if dt.datetime.fromisoformat(c["lastMessage"]) >= desde:
            saida.append(c)
    return saida


def ler_chat(jid, dias=DIAS):
    return wa("read", jid, "--days", str(dias), "--limit", str(POR_CHAT))


def analisar(chat, dados):
    """Devolve o item pendente da conversa, ou None se não há nada esperando o usuário."""
    ms = sorted(dados.get("messages") or [], key=lambda m: m.get("ts", 0))
    if not ms:
        return None
    grupo = bool((dados.get("chat") or {}).get("isGroup", chat.get("isGroup")))
    nome = (dados.get("chat") or {}).get("name") or chat.get("name") or chat["jid"]
    minha_ultima = max((m["ts"] for m in ms if m.get("sender") == "me"), default=0)
    depois = [m for m in ms if m.get("ts", 0) > minha_ultima and m.get("sender") != "me"]
    if not depois:
        return None
    if grupo:
        gatilhos = [m for m in depois if "@me" in (m.get("mentioned") or [])]
        motivo = "marcou você"
        if not gatilhos:
            rx = citacao()
            gatilhos = [m for m in depois if rx.search(sem_acento(texto(m)))]
            motivo = "citou seu nome"
        if not gatilhos:
            return None
        desde = gatilhos[0]
    else:
        motivo = "última mensagem não é sua"
        desde = depois[0]
    ultima = ms[-1]
    # conversa que termina num "ok", "blz", "valeu", emoji... quase sempre já está encerrada
    fechamento = not grupo and all(FECHO.fullmatch(texto(m).lower().strip(" .!")) for m in depois)
    return {
        "fechamento": fechamento,
        "chave": chat["jid"],
        "nome": nome,
        "tipo": "grupo" if grupo else "privado",
        "motivo": motivo,
        "desde_ts": desde["ts"],
        "ultima_ts": ultima["ts"],
        "ultima_id": ultima.get("id"),
        "sem_resposta": len(depois),
        "quem": desde.get("sender") or "?",
        # grupo: a mensagem que te marcou primeiro, depois o fim da conversa; privado: o fim da conversa
        "previa": ([compacta(desde)] + [compacta(m) for m in ms[-2:] if m is not desde]) if grupo
                  else [compacta(m) for m in ms[-4:]],
    }


# ---------- visão de operação: ocorrências e atividade nos grupos (mesmo sem marcar o usuário) ----------
def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


CRITICO = re.compile(
    r"desarm|\btrip\b|tripou|disparou|usina (parada|caiu|desligou|fora)|parada total|sem geracao|geracao zerad|"
    r"zerou a geracao|incendio|\bfogo\b|fumaca|explos|curto[- ]?circuito|acidente|choque eletrico|emergencia|"
    r"falta de energia|apagao|religador (abriu|atuou|desarmou)|disjuntor (geral )?(abriu|atuou|desarmou)|"
    r"protecao (atuou|atuada)|rele (atuou|atuado)|bloqueio da protecao")
ALERTA = re.compile(
    r"alarme|alarmando|\bfalha|\berro\b|sem comunicacao|perda de comunicacao|comunicacao (caiu|parou|oscilando)|"
    r"\boffline\b|fora do ar|inversor(es)? (parad|deslig|com falha|em falha|off\b)|sobretemperatura|superaquec|"
    r"temperatura (alta|elevada)|baixa (geracao|performance)|\bdefeito|anomalia|\burgente|queimad|queimou|"
    r"\bparad[oa]s?\b|desligad[oa]")
NORMAL = re.compile(
    r"normaliza|restabelec|reestabelec|\bvoltou\b|voltaram|retornou|retornaram|resolvid|religad|religamento|"
    r"operando normal|em operacao normal|ja (esta|estao) (gerando|operando)|gerando normal|disjuntor (52l )?fechado")
BOLETIM = re.compile(r"atualizacao das usinas|status operacional|geracao diaria|relatorio diario|resumo do dia")
SO_COMUNICACAO = re.compile(r"falha de comunicacao|sem comunicacao|perda de comunicacao")
GRAVE = re.compile(r"desarm|disjuntor|\btrip|tripou|parada|emergencial|incendio|acidente|protecao|rele")
# "*UFV PTY100 – Paty dos Alferes 100 (Avelar)*", "Usina: UFV CDB100 – Candiba"
CODIGO = re.compile(r"UFV\s+([A-Z]{2,4}\d{3}(?:/\d{3})?)(?:\s*[–—-]\s*([^*\n>|]{2,60}))?")
PROGRAMADA = re.compile(r"atividade( cancelada)?:|preventiva|programad[ao]|manutencao planejada")
# usina ainda parada esperando alguém: "enviar um terceiro amanhã para religar", "vai ficar desligado"
PENDENTE = re.compile(r"\b(para|pra|p/)\s+(religar|rearmar|restabelecer|energizar|fechar o disjuntor)\b|"
                      r"\b(vai|vao|ira|irao)\s+(estar|ficar|continuar)\s+(desligad|parad|fora)|"
                      r"\b(continua|segue|permanece)\s+(desligad|parad|desarmad|fora)")
USINA = re.compile(r"\bUFVs?\b|\busina", re.I)
JANELA = 24 * 3600     # ocorrências e atividade das últimas 24 h
MONTAGEM = JANELA  # ocorrências montadas com as últimas 24 h (3 dias deixava críticas velhas abertas para sempre);
                   # a identidade entre remontagens fica com as marcações, que guardam as mensagens (servidor.py)
SEM_REGISTRO = 24 * 3600  # crítica sem aviso novo por esse tempo sai como "sem registro de normalização"
INATIVIDADE = 6 * 3600  # alerta sem aviso novo por esse tempo sai sozinho (crítica de usina não: precisa de normalização)
JUNTAR = 3 * 3600      # alertas da mesma usina, sem normalização no meio e com menos que isso de intervalo, são uma ocorrência só
PALAVRAS_VAZIAS = {"ufv", "ufvs", "usina", "usinas", "gerar", "gera", "cog", "elis", "energia", "grupo", "dos", "das",
                   "del", "sobreaviso", "solar", "interno", "time", "sup", "equipe", "local", "eng", "manutencao"}
ROMANOS = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}


def rotulo_usina(nome):
    """'ÉLIS - UFV CAMPINORTE/GO' -> 'UFV CAMPINORTE/GO'; 'UFV Rajada-PE Gerar' -> 'UFV Rajada-PE'."""
    m = re.search(r"\bUFVs?\b.*", nome, re.I)
    r = (m.group(0) if m else nome)
    r = re.sub(r"\s+(gerar|gera|o&m|om|cog|grupo)\b.*$", "", r, flags=re.I).strip(" -|")
    return r[:38] or nome[:38]


def assinatura(nome):
    """Palavras e números de um nome de usina, para casar 'Paty dos Alferes 100' com 'UFV Paty do Alferes'."""
    s = sem_acento(nome)
    palavras = {p for p in re.findall(r"[a-z]{3,}", s) if p not in PALAVRAS_VAZIAS}
    numeros = set(re.findall(r"\d+", s)) | {ROMANOS[p] for p in re.findall(r"\b(i{1,3}|iv|v|vi)\b", s)}
    return palavras, numeros


def mesma_usina(a, b):
    pa, na = a
    pb, nb = b
    return bool(pa & pb) and (not na or not nb or bool(na & nb))


# ---------- normalização: só aceita fato consumado ----------
# forte: o COG avisa normalização estruturada, ou alguém afirma que a usina/equipamento voltou
NORMAL_COG = re.compile(r"🟩|normalizacao:|atendimento concluido|usina restabelecida")
# fim do atendimento dito pelo técnico ou pelo COG: "PD encerra aqui a OS", "pode encerrar a OS", "OS finalizada"
FIM_OS = re.compile(r"\b(pode|pd|podem|pode-se)\s+(encerrar|encerra|fechar|finalizar|baixar)\s+(aqui\s+)?(a\s+)?os\b|"
                    r"\bos\s+(\d+\s+)?(encerrada|finalizada|concluida|fechada)\b|"
                    r"\batendimento\s+(finalizado|encerrado|concluido)\b")
TECNICO = re.compile(r"T[ée]cnico acionado:\s*([A-ZÀ-Ú][\wÀ-ú]+(?:\s+[A-ZÀ-Ú][\wÀ-ú]+)?)")
NORMAL_FATO = re.compile(
    r"\b(normalizad[oa]s?|restabelecid[oa]s?|reestabelecid[oa]s?|religad[oa]s?|rearmad[oa]s?)\b|"
    r"\b(voltou|voltaram|retornou|retornaram)\b(?! a (falhar|cair|desarmar|alarmar))|"
    r"\b(ja )?(esta|estao|segue|seguem) (gerando|operando|comunicando|normal)\b|"
    r"\bgerando normal|\boperando normal|"
    r"\bfoi realizad[oa] o? ?(fechamento|religamento|rearme)\b|\bfechamento realizado\b")
# o que desfaz a afirmação, quando aparece pouco antes da palavra
NEGACAO = re.compile(r"\b(nao|n|nem|nunca|sem|ainda nao)\s+(\w+\s+){0,2}$")
INTENCAO = re.compile(r"\b(vou|vamos|irei|iremos|vai|vao|para|pra|se|posso|pode|podemos|podem|aguardando|aguardar|"
                      r"solicitar|informar|verificar|tentar|ate|antes de|quando|assim que|caso|deve|precisa)\b(\s+\S+){0,4}\s*$")
CONTRASTE = re.compile(r"\b(porem|mas|entretanto|contudo|so que)\b")
HESITACAO = re.compile(r"\b(parece|parecia|acho|acredito|talvez|aparentemente|possivelmente|provavelmente|deve ter|teoricamente)\b")
# problema relatado no resto da mensagem (afirmação mista: "foi religado... o disjuntor da usina abriu")
PROBLEMA = re.compile(r"\b(abriu|abriram|saltou|caiu|desarm\w*|trip\w*|sem comunicacao|perda de comunicacao|"
                      r"falha\w*|alarm\w*|parad[oa]s?|deslig\w*|queim\w*|defeito|anomalia)\b")
# ...a não ser que seja só a causa do que já foi resolvido ("por conta da falha do smartlogger")
CAUSA = re.compile(r"(por conta d\w*|devido a\w*|causad\w* por|que apresentava\w*|apresentavam|estava\w*|havia|tinha\w*|"
                   r"motivo d\w*|diante d\w*|nao|sem|nem)\s+(\S+\s+){0,3}$")


def _problema_ativo(trecho):
    """Há algum problema relatado no trecho que não seja só a causa já explicada ou uma negação?"""
    for p in PROBLEMA.finditer(trecho):
        if not CAUSA.search(trecho[max(0, p.start() - 40):p.start()]):
            return True
    return False


def _frases(t):
    """Divide em frases, mantendo o ponto final de cada uma (para saber se é pergunta)."""
    return [f.strip() for f in re.findall(r"[^.!?\n]+[.!?]*", t) if f.strip()]


PARADA_NOME = re.compile(r"^(relig|normaliz|restabelec|reestabelec|desarm|parad|deslig|rearm|volt|retorn|sem|com|foi|esta|estao|"
                         r"segue|tripou|caiu|teve|apresent|precis|esta|gerando|operando|online|offline|ok)", re.I)


def extrair_nome_usina(bruto):
    """'UFV Monsenhor Tabosa religada.' -> 'Monsenhor Tabosa'. Só palavras com inicial maiúscula (ou números) logo
    depois de 'UFV', parando em palavras de status. None se a mensagem não nomeia uma usina."""
    m = re.search(r"\bUFVs?\s+((?:[A-ZÀ-Ú0-9][\wÀ-ú'´-]*\.?\s*){1,4})", bruto)
    if not m:
        return None
    nome = []
    for p in m.group(1).split():
        p = p.strip(".,;:!?*")
        if not p or PARADA_NOME.match(sem_acento(p)) or (nome and p.lower() in ("de", "do", "da", "dos", "das", "e")):
            break
        nome.append(p)
    nome = " ".join(nome)
    return nome if len(nome) >= 3 and not re.fullmatch(r"[A-Z]{2,4}\d{3}", nome) else None


VOLTA_USINA = re.compile(r"\b(religad|rearmad|restabelecid|reestabelecid|normalizad)\w*\b.*\b(usina|ufv|projeto|disjuntor|gera)|"
                         r"\b(usina|ufv|projeto)\b.*\b(religad|rearmad|restabelecid|reestabelecid|normalizad|voltou|retornou|gerando)|"
                         r"\b(gerando|em geracao|disjuntor (52l )?fechado|fechamento (do disjuntor|realizado)|rearm)|^(usina )?religad|"
                         r"atendimento concluido|normalizacao:|encerr\w* (a|aqui a)? ?os|os \d* ?(encerrada|finalizada|concluida)")


def so_comunicacao(t):
    """A normalização fala só da comunicação ("comunicação do relé LT retornou"), sem dizer que a usina voltou a gerar?
    Isso fecha alerta de comunicação, mas não uma crítica de desarme."""
    return bool(re.search(r"comunica|logger|scada|monitoramento|online|sinal", t)) and not VOLTA_USINA.search(t)


def eh_normalizacao(t):
    """t sem acento. True só quando a mensagem afirma que já normalizou: não vale pergunta ("voltou?"),
    negação ("não retornou"), intenção ("vou restabelecer", "pode informar o religamento") nem
    afirmação desfeita depois ("disjuntor fechado, porém a usina não comunica")."""
    if (NORMAL_COG.search(t) or FIM_OS.search(t)) and "🟥" not in t and not t.rstrip().endswith("?"):
        return True
    for f in _frases(t):
        m = NORMAL_FATO.search(f)
        if not m:
            continue
        antes, depois = f[:m.start()], f[m.end():]
        if f.rstrip().endswith("?") or NEGACAO.search(antes) or INTENCAO.search(antes) or HESITACAO.search(antes):
            continue
        # mensagem mista: um problema relatado no resto da mensagem desfaz a normalização
        resto = t.replace(f, " ") + " " + antes
        if _problema_ativo(resto):
            continue
        c = CONTRASTE.search(depois)
        if c and (ALERTA.search(depois[c.end():]) or CRITICO.search(depois[c.end():]) or re.search(r"\b(nao|sem)\b", depois[c.end():])):
            continue
        return True
    return False


def classificar(t):
    """t já sem acento. Devolve 'normal', 'critico', 'alerta', 'boletim' ou None."""
    if BOLETIM.search(t):
        return "boletim"
    if PROGRAMADA.search(t) and "🟥" not in t.split("atividade", 1)[0]:
        return None
    if "🟩" in t and t.rfind("🟩") > t.rfind("🟥"):
        return "normal"  # resumo do COG: "🟥 Ocorrência ... 🟩 Normalização" — terminou normalizada
    if "🟥" not in t and eh_normalizacao(t):
        return "normal"
    if PENDENTE.search(t):
        return "critico"
    if CRITICO.search(t):
        return "alerta" if SO_COMUNICACAO.search(t) and not GRAVE.search(t) else "critico"
    if ALERTA.search(t) or "🟥" in t:
        return "alerta"
    return None


CORRECAO = re.compile(r"^(mas|porem|so que|entretanto|contudo)\b|\bainda\b.*\b(abaixo|baixa|nao|sem|falha|oscil|parad|deslig)|"
                      r"\bnao (segur|aguent|vai segurar)|\bvoltou a (cair|desarmar|falhar)")


def desmentida(m, mensagens):
    """A mesma pessoa corrigiu logo depois ("Mas ainda tá abaixo dos 5%.. usina talvez não segure")?"""
    for x in mensagens:
        if x is m or x.get("sender") != m.get("sender"):
            continue
        if 0 < x.get("ts", 0) - m.get("ts", 0) <= 300:
            tx = sem_acento(texto(x))
            if CORRECAO.search(tx) or (_problema_ativo(tx) and not eh_normalizacao(tx)):
                return True
    return False


def operacao(chat, dados, agora=None, janela=None):
    """Eventos de operação (alarme, normalização, boletim) e atividade por hora de um grupo, nas últimas 24 h.
    As ocorrências são montadas depois, juntando os eventos de todos os grupos (ver montar_ocorrencias)."""
    agora = agora or time.time()
    ms = sorted(dados.get("messages") or [], key=lambda m: m.get("ts", 0))
    grupo = bool((dados.get("chat") or {}).get("isGroup", chat.get("isGroup")))
    nome = (dados.get("chat") or {}).get("name") or chat.get("name") or chat["jid"]
    # as ocorrências são montadas com tudo o que foi lido (3 dias): assim o primeiro aviso não sai da janela
    # no meio de uma ocorrência longa e ela não "renasce" com outra identificação; atividade e feed são de 24 h
    base = [m for m in ms if m.get("ts", 0) >= agora - (janela or MONTAGEM)]
    recentes = [m for m in ms if m.get("ts", 0) >= agora - JANELA]
    horas = {}
    for m in recentes:
        h = int(m["ts"] // 3600 * 3600)
        horas[h] = horas.get(h, 0) + 1
    if not grupo:
        return {"horas": horas, "eventos": [], "usina": None, "feed": []}
    de_uma_usina = bool(USINA.search(nome))
    eventos = []
    for m in base:
        bruto = texto(m)
        t = sem_acento(bruto)
        if not t or t.startswith("["):
            continue
        tipo = classificar(t)
        if tipo == "normal" and desmentida(m, base):
            tipo = None
        if not tipo:
            continue
        cod = CODIGO.search(bruto)
        if cod:
            nome_cod = re.split(r"[\u2190-\u2bff\U0001F000-\U0001FFFF]|\.\s|\s{2,}|Local:|OS:", cod.group(2) or "")[0]
            nome_cod = nome_cod.strip(" .,;:*")
            usina = f"{cod.group(1)} – {nome_cod}" if nome_cod else cod.group(1)
            chave = cod.group(1)
        elif de_uma_usina:
            usina, chave = rotulo_usina(nome), chat["jid"]
        else:
            # grupo geral (Solar Interno, O&M...): a usina vem do nome citado na mensagem, se houver
            citada = extrair_nome_usina(bruto)
            if citada:
                usina, chave = "UFV " + citada, "nome:" + citada
            elif tipo == "normal":
                # "religada!" num grupo geral sem dizer qual usina: só vale se quem fala é o técnico acionado
                # de uma ocorrência (resolvido depois, em montar_ocorrencias); senão não fecha nada
                usina, chave = nome[:38], "tecnico:" + sem_acento(m.get("sender") or "")
            else:
                usina, chave = nome[:38], chat["jid"]
        ev = {"tipo": tipo, "ts": m["ts"], "id": m.get("id"), "jid": chat["jid"], "grupo": nome,
              "usina": usina, "chave_usina": chave, "msg": compacta(m),
              "codigo": cod.group(1) if cod else None, "nome_codigo": nome_cod if cod else None,
              "tecnico": (TECNICO.search(bruto).group(1) if TECNICO.search(bruto) else None),
              "generico": not cod and not de_uma_usina and chave == chat["jid"],
              "motivo": ("cog" if NORMAL_COG.search(t) else "mensagem") if tipo == "normal" else None,
              "so_comunicacao": tipo == "normal" and so_comunicacao(t)}
        if tipo == "boletim":
            ev["completo"] = (m.get("text") or bruto).replace("*", "")[:3000]  # texto original, com as quebras de linha
        eventos.append(ev)
    usina = None
    if de_uma_usina:
        citados = {}
        for m in ms:
            for c in re.findall(r"UFV\s+([A-Z]{2,4}\d{3})\b", m.get("text") or ""):
                citados[c] = citados.get(c, 0) + 1
        usina = {"jid": chat["jid"], "nome": rotulo_usina(nome), "grupo": nome, "citados": citados,
                 "msgs_24h": len(recentes), "ultima_ts": ms[-1]["ts"] if ms else None,
                 "ultima": compacta(ms[-1]) if ms else None}
    feed = [dict(compacta(m), grupo=nome) for m in recentes[-15:]]
    return {"horas": horas, "eventos": eventos, "usina": usina, "feed": feed}


def vincular_codigos(usinas, vinculos=None):
    """Descobre de qual grupo de usina é cada código do COG. Devolve {código: jid}.
    vinculos: {"UBE100": "UFV UBL 100-MG Gerar" ou jid} (manual, tem prioridade; vem de vinculos.json)."""
    por_nome = {u["grupo"].lower(): u["jid"] for u in usinas}
    por_nome.update({u["nome"].lower(): u["jid"] for u in usinas})
    dono = {}
    # aprendido: o código citado ao menos 2 vezes num grupo de usina é dela (se citado em vários, fica com quem cita mais)
    melhor = {}
    for u in usinas:
        for c, n in (u.get("citados") or {}).items():
            if n >= 2 and n > melhor.get(c, (0, None))[0]:
                melhor[c] = (n, u["jid"])
    dono.update({c: jid for c, (n, jid) in melhor.items()})
    for c, alvo in (vinculos or {}).items():  # manual por cima de tudo
        jid = alvo if "@" in alvo else por_nome.get(str(alvo).lower())
        if jid:
            dono[c.upper()] = jid
    for u in usinas:  # o código principal do grupo: o que mais aparece nele (é o mesmo do KMZ)
        meus = {c: (u.get("citados") or {}).get(c, 0) for c, j in dono.items() if j == u["jid"]}
        if meus:
            u["codigo"] = max(meus, key=meus.get)
            u["codigos"] = sorted(meus)
    return dono


def montar_ocorrencias(eventos, usinas, vinculos=None):
    """Junta os eventos de todos os grupos em ocorrências por usina. O mesmo aviso do COG postado em
    dois grupos vira uma ocorrência só; uma normalização da usina fecha a ocorrência aberta dela."""
    for u in usinas:
        u["assinatura"] = assinatura(u["nome"])
    # a chave de cada evento: o código (PTY100), ou o grupo da usina; um código que casa com o nome de um
    # grupo de usina passa a usar o grupo, para o quadro de usinas ficar num lugar só
    dono = vincular_codigos(usinas, vinculos)
    por_codigo = dict(dono)
    for e in eventos:
        if e["chave_usina"] == e["jid"]:
            continue
        cod = e["chave_usina"]
        if cod not in por_codigo:
            nome_cod = e["usina"].split("–", 1)[-1] if "–" in e["usina"] else re.sub(r"(\d+)", r" \1", cod)
            alvo = next((u for u in usinas if mesma_usina(assinatura(nome_cod), u["assinatura"])), None)
            por_codigo[cod] = alvo["jid"] if alvo else cod
        e["chave_usina"] = por_codigo[cod]
    nomes_codigo = {}
    for e in eventos:
        if e.get("codigo") and e.get("nome_codigo"):
            nomes_codigo[e["codigo"]] = assinatura(e["nome_codigo"])
    resolvidos = {}
    for e in eventos:
        if not str(e["chave_usina"]).startswith("nome:"):
            continue
        citada = e["chave_usina"][5:]
        if citada not in resolvidos:
            ass = assinatura(citada)
            alvo = next((u["jid"] for u in usinas if mesma_usina(ass, u["assinatura"])), None)
            if not alvo:
                cod = next((c for c, a in nomes_codigo.items() if mesma_usina(ass, a)), None)
                alvo = por_codigo.get(cod, cod) if cod else None
            # sem dono conhecido: a própria grafia normalizada vira a chave (junta "Concórdia" e "CONCORDIA")
            resolvidos[citada] = alvo or "nome:" + " ".join(sorted(ass[0])) + " " + " ".join(sorted(ass[1]))
        e["chave_usina"] = resolvidos[citada]
    ocorrencias, abertas, boletins = [], {}, []
    for e in sorted(eventos, key=lambda e: e["ts"]):
        k = e["chave_usina"]
        if e["tipo"] == "boletim":
            boletins.append(e)
            continue
        if str(k).startswith("tecnico:"):
            # o técnico acionado numa ocorrência aberta (e citado pelo primeiro nome) fecha só a dele, e só no mesmo grupo
            quem = k[8:]
            alvo = [x for x in abertas.values() if not x["normalizado"] and x.get("tecnico") and e["jid"] in x["jids"]
                    and sem_acento(x["tecnico"]).split()[0] in quem.split()]
            if len(alvo) != 1:
                continue  # ninguém, ou mais de uma ocorrência com esse técnico: não dá para saber qual fechar
            k = alvo[0]["chave_usina"]
        o = abertas.get(k)
        if e["tipo"] == "normal":
            if o and not o["normalizado"] and o["sev"] == "critico" and e.get("so_comunicacao"):
                continue  # voltou a comunicação, mas a usina desarmada não foi dada como religada
            if o and not o["normalizado"]:
                o["normalizado"] = dict(e["msg"], grupo=e["grupo"], motivo=e.get("motivo") or "mensagem")
                o["jids"] = sorted(set(o["jids"]) | {e["jid"]})
                o["fim_ts"] = e["ts"]
            continue
        if o and not o["normalizado"]:
            o["tecnico"] = o.get("tecnico") or e.get("tecnico")
            o["ultima_ts"] = e["ts"]
            o["qtd"] += 1
            o["grupos"] = sorted(set(o["grupos"]) | {e["grupo"]})
            o["jids"] = sorted(set(o["jids"]) | {e["jid"]})
            o["ids"].append(e["id"])
            if e["tipo"] == "critico" and o["sev"] != "critico":
                o["sev"], o["msg"] = "critico", e["msg"]
            continue
        if o and o["normalizado"] and e["ts"] - o["fim_ts"] <= 10 * 60:
            continue  # o mesmo aviso repetido em outro grupo logo depois da normalização
        o = {"chave": f"{k}|{e['id']}", "usina": e["usina"], "chave_usina": k, "jid": e["jid"], "grupos": [e["grupo"]],
             "sev": e["tipo"], "inicio_ts": e["ts"], "ultima_ts": e["ts"], "qtd": 1, "msg": e["msg"],
             "jids": [e["jid"]], "ids": [e["id"]], "generico": e.get("generico", False), "tecnico": e.get("tecnico"),
             "normalizado": None}
        abertas[k] = o
        ocorrencias.append(o)
    agora = time.time()
    for o in ocorrencias:
        if o["normalizado"] or agora - o["ultima_ts"] < INATIVIDADE:
            continue
        if o["sev"] == "alerta" or o.get("generico"):
            o["normalizado"] = {"ts": o["ultima_ts"] + INATIVIDADE, "de": "painel", "motivo": "inatividade",
                                "texto": f"sem avisos novos há {INATIVIDADE // 3600} h: baixa automática por inatividade"}
            o["fim_ts"] = o["normalizado"]["ts"]
        elif agora - o["ultima_ts"] >= SEM_REGISTRO:
            # crítica sem nenhum aviso novo por 24 h: sai das abertas como "sem registro" (o COG fala de usina
            # parada pelo menos uma vez por dia; se ninguém falou mais nada, não fica aberta para sempre)
            o["normalizado"] = {"ts": o["ultima_ts"] + SEM_REGISTRO, "de": "painel", "motivo": "sem_registro",
                                "texto": "24 h sem nenhum aviso novo e sem normalização registrada no WhatsApp"}
            o["fim_ts"] = o["normalizado"]["ts"]
    # estado de cada usina para o quadro: pior ocorrência aberta das últimas 24 h
    extras = {}
    for o in ocorrencias:
        alvo = next((u for u in usinas if u["jid"] == o["chave_usina"]), None)
        if not alvo and "@" in o["chave_usina"]:
            continue  # grupo geral (Solar Interno, Engenharia...) sem código de usina na mensagem
        if not alvo:
            alvo = extras.setdefault(o["chave_usina"], {"jid": o["chave_usina"], "nome": "UFV " + o["usina"], "codigo": o["chave_usina"],
                                                         "grupo": ", ".join(o["grupos"]), "msgs_24h": None,
                                                         "ultima_ts": o["ultima_ts"], "ultima": o["msg"]})
        alvo.setdefault("ocorrencias", []).append(o)
    todas = usinas + list(extras.values())
    for u in todas:
        oc = u.get("ocorrencias", [])
        abertas_u = [o for o in oc if not o["normalizado"]]
        u["estado"] = "critico" if any(o["sev"] == "critico" for o in abertas_u) else "alerta" if abertas_u else \
                      "normalizado" if oc else ("ativa" if u.get("msgs_24h") else "quieta")
        u["abertas"] = len(abertas_u)
        u.pop("ocorrencias", None)
        u.pop("assinatura", None)
    return ocorrencias, todas, boletins


def diario(qual):
    """Linhas da planilha, pelo próprio diario.py (listar). Sem Diário configurado: lista vazia, sem erro."""
    py, script = config.diario()
    if not script:
        return [], None
    try:
        r = subprocess.run([py, script, "listar", qual], capture_output=True, text=True, timeout=60, encoding="utf-8")
        if r.returncode:
            return [], r.stderr.strip()[:200] or "diario.py falhou"
        return json.loads(r.stdout), None
    except Exception as e:
        return [], str(e)


ABERTO_CHAMADO = ("pendente", "em andamento", "aguardando", "em aberto", "aberto")
ABERTO_TAREFA = ("pendente", "em andamento", "aguardando", "atrasada")


def aberto(status, tipo):
    s = (status or "").strip().lower()
    return s in (ABERTO_CHAMADO if tipo == "chamado" else ABERTO_TAREFA)


VINCULOS = os.path.join(config.DADOS, "vinculos.json")


def ler_vinculos():
    try:
        with open(VINCULOS, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def coletar(cache=None, dias=DIAS, log=print):
    """Sincronização completa. `cache` guarda, por jid, o lastMessage e o item já analisado, para não
    reler conversas que não mudaram."""
    cache = cache if cache is not None else {}
    inicio = time.time()
    pendentes, erros = [], []
    eventos, usinas, feed, horas = [], [], [], {}
    vinculos = ler_vinculos()
    chats = chats_ativos(dias)
    # a cada hora cheia as janelas de 24 h andam: reanalisa tudo (sem reler, os dados ficam no cache)
    hora_atual = int(time.time() // 3600)
    for c in chats:
        jid = c["jid"]
        guardado = cache.get(jid)
        if guardado and guardado.get("lastMessage") == c.get("lastMessage"):
            dados = guardado["dados"]
            item = guardado["item"]
            op = guardado["op"] if guardado.get("hora") == hora_atual else operacao(c, dados)
        else:
            try:
                dados = ler_chat(jid, dias)
                item, op = analisar(c, dados), operacao(c, dados)
            except Exception as e:
                erros.append(f"{c.get('name') or jid}: {e}")
                if not guardado:
                    continue
                dados, item, op = guardado["dados"], guardado["item"], guardado["op"]
        cache[jid] = {"lastMessage": c.get("lastMessage"), "dados": dados, "item": item, "op": op, "hora": hora_atual}
        if item:
            pendentes.append(item)
        eventos += op["eventos"]
        feed += op["feed"]
        if op["usina"]:
            usinas.append(dict(op["usina"]))
        for h, n in op["horas"].items():
            horas[h] = horas.get(h, 0) + n
    for jid in list(cache):
        if jid not in {c["jid"] for c in chats}:
            del cache[jid]
    pendentes.sort(key=lambda i: i["desde_ts"])
    codigos = {e["codigo"]: e["nome_codigo"] for e in sorted(eventos, key=lambda e: e["ts"]) if e.get("codigo") and e.get("nome_codigo")}
    ocorrencias, usinas, boletins = montar_ocorrencias(eventos, usinas, vinculos)
    cod_grupo = {u["jid"]: u.get("codigo") for u in usinas if u.get("codigo")}
    for o in ocorrencias:  # o código do COG, quando houver, para achar a usina no mapa
        o["codigo"] = cod_grupo.get(o["chave_usina"]) or \
            next((e["codigo"] for e in eventos if e.get("codigo") and e["chave_usina"] == o["chave_usina"]), None)
    for u in usinas:
        u["codigo"] = u.get("codigo") or next((e["codigo"] for e in eventos if e.get("codigo") and e["chave_usina"] == u["jid"]), None)
    limite = time.time() - JANELA
    ocorrencias = [o for o in ocorrencias if not o["normalizado"] or o["ultima_ts"] >= limite
                   or o["normalizado"].get("ts", 0) >= limite]
    ocorrencias.sort(key=lambda o: (o["normalizado"] is not None, -o["ultima_ts"]))
    boletins.sort(key=lambda b: -b["ts"])
    feed.sort(key=lambda m: -m["ts"])
    ordem = {"critico": 0, "alerta": 1, "normalizado": 2, "ativa": 3, "quieta": 4}
    usinas.sort(key=lambda u: (ordem[u["estado"]], -(u["ultima_ts"] or 0)))
    inicio_h = int((time.time() - JANELA) // 3600 * 3600) + 3600
    atividade = [{"h": h, "n": horas.get(h, 0)} for h in range(inicio_h, int(time.time()) + 1, 3600)]
    chamados, e1 = diario("chamados")
    tarefas, e2 = diario("tarefas")
    for e in (e1, e2):
        if e:
            erros.append(f"Diário: {e}")
    log(f"sincronizado em {time.time() - inicio:.0f}s: {len(chats)} conversas, {len(pendentes)} pendentes, "
        f"{len(ocorrencias)} ocorrências, {len(chamados)} chamados, {len(tarefas)} tarefas"
        + (f", {len(erros)} erro(s)" if erros else ""))
    return {"quando": int(time.time()), "whatsapp": status(), "pendentes": pendentes,
            "ocorrencias": ocorrencias[:120], "usinas": usinas, "boletins": boletins[:6], "codigos": codigos, "feed": feed[:60], "atividade": atividade,
            "chamados": chamados, "tarefas": tarefas, "erros": erros}


if __name__ == "__main__":
    dias = int(sys.argv[sys.argv.index("--dias") + 1]) if "--dias" in sys.argv else DIAS
    d = coletar(dias=dias, log=lambda s: print(s, file=sys.stderr))
    for o in d["ocorrencias"]:
        print(f"{o['sev']:8} {'NORMALIZADO ' if o['normalizado'] else ''}{time.strftime('%d/%m %H:%M', time.localtime(o['inicio_ts']))} "
              f"{o['usina'][:30]:30} x{o['qtd']} [{len(o['grupos'])} grupos] {o['msg']['de']}: {o['msg']['texto'][:80]}")
    for b in d['boletins']:
        print('BOLETIM', time.strftime('%d/%m %H:%M', time.localtime(b['ts'])), b['grupo'][:30], b['msg']['texto'][:80])
    print()
    for u in d["usinas"]:
        print(f"{u['estado']:11} {u['nome'][:40]:40} {u['msgs_24h'] or 0:4} msgs/24h  {u['abertas']} abertas")
    print()
    for p in d["pendentes"]:
        espera = (time.time() - p["desde_ts"]) / 3600
        print(f"{espera:5.1f} h  {p['tipo']:7} {p['nome'][:40]:40} {p['motivo']} ({p['quem']}): {p['previa'][-1]['texto'][:80]}")
    print(f"\n{len(d['pendentes'])} pendentes · {sum(aberto(c.get('status'), 'chamado') for c in d['chamados'])} chamados abertos · "
          f"{sum(aberto(t.get('status'), 'tarefa') for t in d['tarefas'])} tarefas abertas", file=sys.stderr)
    for e in d["erros"]:
        print("erro:", e, file=sys.stderr)
