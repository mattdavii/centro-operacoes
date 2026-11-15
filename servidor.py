#!/usr/bin/env python3
# Centro de Operações: painel local de plantão sobre o wa-app (WhatsApp, só leitura).
# Sincroniza com o wa-app (só leitura) a cada minuto e serve a página em http://127.0.0.1:47900
# As marcações feitas no painel (respondi, resolvido, ignorar, lembrar depois) ficam em acoes.json,
# só neste computador; nada é escrito no WhatsApp nem na planilha.
import hmac, http.server, ipaddress, json, mimetypes, os, re, sys, threading, time, traceback, urllib.parse

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
import clima, coletor, config, indicadores, mapa, relatorio  # noqa: E402

PORTA = int(os.environ.get("ATENDIMENTOS_PORTA") or config.carregar().get("porta") or 47900)
INTERVALO = 60
DADOS = config.DADOS
ACOES = os.path.join(DADOS, "acoes.json")
PLANTAO = os.path.join(DADOS, "plantao.json")  # {"inicio": "2026-11-14T00:00", "fim": "2026-11-16T08:00", "equipe": [...]}

trava = threading.Lock()
estado = {"dados": None, "sincronizando": False, "erro": None, "cache": {}, "teste": None}
TESTE_DURA = 180  # o alarme de teste fica "aberto" por 3 min, o suficiente para o celular consultar e tocar


def ler_acoes():
    try:
        with open(ACOES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def gravar_acoes(acoes):
    os.makedirs(os.path.dirname(ACOES), exist_ok=True)
    tmp = ACOES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(acoes, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ACOES)


def _plantao_bruto():
    try:
        with open(PLANTAO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _plantao_gravar(p):
    os.makedirs(DADOS, exist_ok=True)
    tmp = PLANTAO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PLANTAO)


def resumo_celular(p):
    """O que o painel do plantão do celular mostra (tela de bloqueio e widget): contadores e as abertas mais importantes."""
    abertas = [o for o in p.get("ocorrencias", []) if not o.get("normalizado") and not o.get("generico")]
    ativas = [o for o in abertas if o.get("status") != "em_tratativa"]
    ordem = {"critico": 0, "alerta": 1}
    ativas.sort(key=lambda o: (ordem.get(o["sev"], 2), -o["ultima_ts"]))
    rot = {"aberto": "em aberto", "cog_validando": "COG validando", "a_caminho": "técnico a caminho", "em_atendimento": "em atendimento"}
    linhas = [("🔴 " if o["sev"] == "critico" else "🟡 ") + coletor.rotulo_usina(o["usina"])[:28] + " · " + rot.get(o.get("status"), "em aberto")
              for o in ativas[:4]]
    if len(ativas) > 4:
        linhas.append(f"+ {len(ativas) - 4} outras")
    try:
        avisos = sorted({a["descricao"] for a in clima.resumo()["avisos"] if clima._em_vigor(a)})
    except Exception:
        avisos = []
    pl = p.get("plantao") or {}
    nome = lambda o: coletor.rotulo_usina(o["usina"])[:40]

    def tempo(o):
        c, pv = o.get("clima_agora") or {}, o.get("clima_previsao") or {}
        return {"agora": c.get("rotulo") if c.get("nivel") else None,
                "previsao": (pv.get("rotulo"), pv.get("quando")) if pv.get("nivel") else None,
                "inmet": [a["descricao"] for a in o.get("aviso_inmet") or []]}

    detalhes = [dict({"usina": nome(o), "codigo": o.get("codigo"), "sev": o["sev"], "status": o.get("status") or "aberto",
                      "desde": o["inicio_ts"], "ultima": o["ultima_ts"], "texto": relatorio._o_que_houve(o)[:160],
                      "motivo": relatorio._limpo((o.get("status_motivo") or "").split(": ", 1)[-1], 110) if o.get("status_origem") != "manual" else ""},
                     **tempo(o)) for o in ativas[:12]]
    tratativa = [{"usina": nome(o), "sev": o["sev"], "desde": o["inicio_ts"],
                  "motivo": relatorio._limpo(re.sub(r"^\s*\*[^*]{0,80}\*", "", (o.get("status_motivo") or "").split(": ", 1)[-1]), 110)
                  if o.get("status_origem") != "manual" else "definido no painel"}
                 for o in abertas if o.get("status") == "em_tratativa"][:10]
    campo = [{"tecnico": x["tecnico"][:30], "usina": coletor.rotulo_usina(x["usina"])[:36], "desde": x["entrada_ts"]}
             for x in p.get("presencas") or [] if not x.get("saida_ts")]
    manut = [{"usina": coletor.rotulo_usina(a["usina"])[:36], "descricao": (a.get("descricao") or "")[:60], "desde": a["inicio_ts"]}
             for a in p.get("atividades") or [] if a.get("status") == "andamento"][:8]
    try:
        cp = clima.painel()
        clima_resumo = {"avisos": [{"descricao": a["descricao"], "severidade": a["severidade"], "fim": a["fim"], "cor": a.get("cor"),
                                    "usinas": len(a["usinas"])} for a in cp["avisos"] if a.get("em_vigor")],
                        "chuva_agora": sum(1 for u in cp["usinas"] if (u.get("atual") or {}).get("nivel")),
                        "temporal_6h": sum(1 for u in cp["usinas"] if (u.get("prox6") or {}).get("nivel") == "severo")}
    except Exception:
        clima_resumo = {"avisos": [], "chuva_agora": 0, "temporal_6h": 0}
    return {"plantao": bool(pl.get("ativo")), "inicio_ts": pl.get("inicio_ts"), "titulo": pl.get("titulo") or "Plantão",
            "equipe": pl.get("equipe") or [],
            "criticas": sum(o["sev"] == "critico" for o in ativas), "alertas": sum(o["sev"] != "critico" for o in ativas),
            "tratativa": len(abertas) - len(ativas),
            "em_campo": len(campo), "linhas": linhas, "inmet": avisos, "quando": p.get("quando"),
            "whatsapp": (p.get("whatsapp") or {}).get("conexao") == "open",
            "ocorrencias": detalhes, "tratativa_lista": tratativa, "campo": campo, "manutencoes": manut, "clima": clima_resumo,
            "resolvidas_24h": sum(1 for o in p.get("ocorrencias", []) if o.get("normalizado") and not o.get("generico")
                                  and time.time() - o["normalizado"].get("ts", 0) < 86400)}


def ler_plantao():
    """Plantão atual (iniciado no botão do painel) e os anteriores, com o relatório de cada um.
    plantao.json: {"atual": {"inicio_ts", "titulo", "equipe"} | null, "historico": [{..., "fim_ts", "relatorio"}]}"""
    p = _plantao_bruto()
    atual = p.get("atual")
    return {"ativo": bool(atual), "inicio_ts": (atual or {}).get("inicio_ts"), "titulo": (atual or {}).get("titulo"),
            "equipe": (atual or {}).get("equipe"), "padrao": p.get("padrao") or {},
            "historico": (p.get("historico") or [])[-10:][::-1]}


def plantao_iniciar(titulo, equipe):
    p = _plantao_bruto()
    if p.get("atual"):
        return p["atual"]
    p["atual"] = {"inicio_ts": int(time.time()), "titulo": titulo or "Plantão", "equipe": equipe or []}
    p["padrao"] = {"titulo": p["atual"]["titulo"], "equipe": p["atual"]["equipe"]}  # sugestão para o próximo
    _plantao_gravar(p)
    return p["atual"]


def plantao_finalizar(painel):
    p = _plantao_bruto()
    atual = p.get("atual")
    if not atual:
        return None
    fim = int(time.time())
    plantao = {"titulo": atual.get("titulo"), "equipe": atual.get("equipe")}
    arquivo = relatorio.salvar(atual["inicio_ts"], fim, painel, plantao)
    item = dict(atual, fim_ts=fim, relatorio=arquivo)
    p["historico"] = (p.get("historico") or []) + [item]
    p["atual"] = None
    _plantao_gravar(p)
    print("plantão finalizado; relatório em", arquivo, flush=True)
    return item


def montar():
    """Junta a última coleta com as marcações do painel. Uma marcação vale até chegar mensagem nova
    na conversa depois dela (aí o item volta para a lista) ou, no caso de "lembrar", até a hora marcada."""
    d = estado["dados"]
    if not d:
        return {"pronto": False, "sincronizando": estado["sincronizando"], "erro": estado["erro"]}
    agora = time.time()
    acoes = ler_acoes()
    aguardando, adiados, resolvidos = [], [], []
    for p in d["pendentes"]:
        a = acoes.get(p["chave"])
        item = dict(p, acao=None)
        if a and p["ultima_ts"] <= a["ts"]:
            if a["tipo"] == "lembrar" and agora < a.get("ate", 0):
                adiados.append(dict(item, acao=a))
                continue
            if a["tipo"] in ("respondi", "resolvido", "ignorar"):
                if a["tipo"] == "resolvido":
                    resolvidos.append(dict(item, acao=a))
                continue
        aguardando.append(item)
    for chave, a in acoes.items():  # resolvidos que já saíram da coleta continuam no histórico do dia
        if a["tipo"] == "resolvido" and agora - a["ts"] < 86400 and not any(r["chave"] == chave for r in resolvidos):
            resolvidos.append({"chave": chave, "nome": a.get("nome", chave), "tipo": a.get("tipo_chat", ""),
                               "acao": a, "previa": []})
    ocorrencias, usinas = ocorrencias_com_acoes(d, acoes)
    try:
        clima.anotar(ocorrencias)  # tempo na usina na hora do início + aviso do INMET em vigor
    except Exception:
        traceback.print_exc()
    atividades, presencas, manut_recentes = manutencoes_com_acoes(d, acoes, ocorrencias, usinas)
    try:
        aplicar_status(ocorrencias, presencas, acoes, usinas)
    except Exception:
        traceback.print_exc()
    abertos = lambda linhas, t: [l for l in linhas if coletor.aberto(l.get("status"), t)]
    # fechados mais recentemente atualizados primeiro (um chamado antigo resolvido hoje aparece em "Resolvidos hoje")
    fechados = lambda linhas: sorted([l for l in linhas if not coletor.aberto(l.get("status"), "chamado")
                                      and not coletor.aberto(l.get("status"), "tarefa")],
                                     key=lambda l: str(l.get("atualizado") or ""), reverse=True)
    return {
        "pronto": True, "sincronizando": estado["sincronizando"], "erro": estado["erro"],
        "quando": d["quando"], "whatsapp": d["whatsapp"], "erros": d["erros"],
        "aguardando": aguardando, "adiados": adiados, "resolvidos": resolvidos,
        "chamados": abertos(d["chamados"], "chamado"), "tarefas": abertos(d["tarefas"], "tarefa"),
        "chamados_fechados": fechados(d["chamados"])[:40], "tarefas_fechadas": fechados(d["tarefas"])[:20],
        "ocorrencias": ocorrencias, "usinas": usinas, "boletins": d["boletins"], "feed": d["feed"], "atividade": d["atividade"],
        "plantao": ler_plantao(), "silencio": ler_silencio(),
        "atividades": atividades, "presencas": presencas, "manut_recentes": manut_recentes,
        "perfil": perfil(), "clima": clima.resumo(), "janela_h": coletor.JANELA_H,
    }


def manutencoes_com_acoes(d, acoes, ocorrencias, usinas):
    """Manutenções e técnicos em campo com as marcações do painel:
    - manutenção em andamento continua no painel mesmo depois de 24 h, até o COG avisar o fim ou você ENCERRAR;
    - depois de 12 h sem "concluída", pergunta "Ainda em manutenção?" (AINDA EM ANDAMENTO adia por mais 12 h);
    - técnico que não avisou a saída: MARCAR SAÍDA.
    Recalcula o "durante manutenção" das ocorrências e os ícones do quadro de usinas."""
    agora = time.time()
    vivas = [dict(a) for a in (d.get("atividades") or [])]
    chaves = {a["chave"] for a in vivas}
    em_andamento_vivo = {(a["chave_usina"], coletor.sem_acento(a["descricao"].lower())) for a in vivas if a["status"] == "andamento"}
    for k, a in relatorio._ler(relatorio.MANUT, {}).items():
        if k not in chaves and a.get("status") == "andamento" and \
           (a["chave_usina"], coletor.sem_acento(a["descricao"].lower())) not in em_andamento_vivo:
            vivas.append(dict(a, fora_da_janela=True))
    for a in vivas:
        fim = acoes.get("fimatv:" + a["chave"])
        if fim and a["status"] == "andamento":
            a.update(status="concluida", fim_ts=fim["ts"], manual=True,
                     fim_msg={"ts": fim["ts"], "de": "você", "texto": "encerrada no painel" + (f": {fim['nota']}" if fim.get("nota") else "")})
        cont = acoes.get("contatv:" + a["chave"])
        a.pop("confirmar", None)
        if a["status"] == "andamento" and agora - max(a["inicio_ts"], cont["ts"] if cont else 0) >= coletor.ATIVIDADE_MAX:
            a["confirmar"] = {"desde": a["inicio_ts"]}
    presencas = [dict(p) for p in (d.get("presencas") or [])]
    for p in presencas:
        s = acoes.get("saida:" + p["chave"])
        if s and not p.get("saida_ts"):
            p.update(saida_ts=s["ts"], saida_manual=True)
    # "durante manutenção": ocorrência que começou com manutenção em andamento na mesma usina
    for o in ocorrencias:
        o["durante_manutencao"] = None
        for a in vivas:
            if a["chave_usina"] == o["chave_usina"] and a["inicio_ts"] - 600 <= o["inicio_ts"] and \
               (a["status"] == "andamento" or (a.get("fim_ts") or 0) >= o["inicio_ts"]):
                o["durante_manutencao"] = {"descricao": a["descricao"], "ate_agora": a["status"] == "andamento"}
                break
    for u in usinas:
        u["manutencao"] = next((a["descricao"] for a in vivas if a["chave_usina"] == u["jid"] and a["status"] == "andamento"), None)
        u["em_campo"] = [p["tecnico"] for p in presencas if p["chave_usina"] == u["jid"] and not p.get("saida_ts")]
    vivas.sort(key=lambda a: (a["status"] != "andamento", -a["inicio_ts"]))
    # concluídas/canceladas dos últimos 7 dias (histórico + o que acabou de fechar)
    recentes = {a["chave"]: a for a in relatorio.manutencoes_periodo(agora - 7 * 86400, agora)[0] if a.get("status") != "andamento"}
    recentes.update({a["chave"]: a for a in vivas if a["status"] != "andamento"})
    return vivas, presencas, sorted(recentes.values(), key=lambda a: -(a.get("fim_ts") or a["inicio_ts"]))[:60]


def acoes_por_mensagem(acoes):
    """{id da mensagem: {"ciente"|"enc"|"keep": ação}} a partir das ocorrências do histórico que têm marcação."""
    hist = relatorio._ler(relatorio.HIST, {})
    out = {}
    for chave, a in acoes.items():
        tipo, base = ("enc", chave[4:]) if chave.startswith("enc:") else ("keep", chave[5:]) if chave.startswith("keep:") \
            else ("acomp", chave[6:]) if chave.startswith("acomp:") else ("st", chave[3:]) if chave.startswith("st:") \
            else ("ciente", chave) if a.get("tipo") == "ciente" else (None, None)
        if not tipo:
            continue
        for mid in set(a.get("ids") or []) | set((hist.get(base) or {}).get("ids") or []):
            out.setdefault(mid, {})[tipo] = a
    return out


STATUS = {"aberto": "Em aberto", "cog_validando": "COG validando", "a_caminho": "Técnico a caminho",
          "em_atendimento": "Em atendimento", "em_tratativa": "Em tratativa", "resolvido": "Resolvido",
          "resolvido_cog": "Resolvido pelo COG"}
TRATATIVA_PERGUNTA = 24 * 3600  # em tratativa: pergunta se continua só depois de 24 h sem novidade


OS_NUM = re.compile(r"\bOS\b\W{0,4}(\d{4,6})\b", re.I)


def status_automatico(o, presencas, jids_usina):
    """Andamento lido nos grupos: entrada/saída do técnico na usina e frases ("em deslocamento", "verificando",
    "amanhã", "aguardando peça"). Devolve (ts, status, motivo) do sinal mais recente, ou None.
    De quebra, anota em o["os"] as OS citadas e em o["visitas"] os técnicos que passaram na usina."""
    ini = o["inicio_ts"] - 600
    fim = (o.get("normalizado") or {}).get("ts") or time.time()
    sinais, oss, visitas = [], set(o.get("os") or []), []
    for p in presencas:
        mesma = p.get("chave_usina") == o.get("chave_usina") or (
            o.get("codigo") and p.get("codigo") and coletor.chave_codigo(p["codigo"]) == coletor.chave_codigo(o["codigo"]))
        if not mesma or p["entrada_ts"] > fim or (p.get("saida_ts") and p["saida_ts"] < ini):
            continue
        sinais.append((max(p["entrada_ts"], ini), "em_atendimento", f"{p['tecnico']} entrou na usina às {time.strftime('%H:%M', time.localtime(p['entrada_ts']))}"))
        visitas.append(f"{p['tecnico']} {time.strftime('%d/%m %H:%M', time.localtime(p['entrada_ts']))}"
                       + (f"–{time.strftime('%H:%M', time.localtime(p['saida_ts']))}" if p.get("saida_ts") and not p.get("sem_saida") else ""))
        if p.get("saida_ts") and not p.get("sem_saida") and p["saida_ts"] <= fim:
            sinais.append((p["saida_ts"], "aberto", f"{p['tecnico']} saiu da usina às {time.strftime('%H:%M', time.localtime(p['saida_ts']))} sem baixa"))
    ids = set(o.get("ids") or [])
    for jid in set(o.get("jids") or [o.get("jid")]):
        msgs = ((estado["cache"].get(jid) or {}).get("dados") or {}).get("messages") or []
        da_usina = jid in jids_usina
        for m in msgs:
            if not (ini <= m.get("ts", 0) <= fim) or not (da_usina or m.get("id") in ids):
                continue
            t = coletor.sem_acento(coletor.texto(m))
            oss.update(OS_NUM.findall(coletor.texto(m)))
            st = coletor.status_da_mensagem(t, coletor.eh_cog(m.get("sender")))
            if st:
                quem = "você" if m.get("sender") == "me" else (m.get("sender") or "?")
                sinais.append((m["ts"], st, f"{quem}: {coletor.texto(m)[:120]}"))
    o["os"] = sorted(oss)
    if visitas:
        o["visitas"] = visitas
    return max(sinais, key=lambda x: x[0]) if sinais else None


def aplicar_status(ocorrencias, presencas, acoes, usinas):
    """Status de cada ocorrência: o automático ou o escolhido no painel, o que for mais recente."""
    jids_usina = {u["jid"] for u in usinas}
    por_msg = acoes_por_mensagem(acoes)
    for o in ocorrencias:
        if o.get("normalizado"):
            if not o.get("os_lidas"):  # OS e visitas, uma vez, para o Diário de Bordo
                status_automatico(o, presencas, jids_usina)
                o["os_lidas"] = True
            manual = acoes.get("st:" + o["chave"])
            if manual and manual.get("status") in ("resolvido", "resolvido_cog"):
                o["status"], o["status_origem"], o["status_motivo"] = manual["status"], "manual", None
            else:
                o["status"] = "resolvido_cog" if coletor.resolvido_pelo_cog(o) else "resolvido"
                o["status_origem"], o["status_motivo"] = "auto", None
            continue
        manual = acoes.get("st:" + o["chave"])
        for mid in o.get("ids") or []:
            a = por_msg.get(mid, {}).get("st")
            if a and (not manual or a["ts"] > manual["ts"]):
                manual = a
        auto = status_automatico(o, presencas, jids_usina)
        if manual and (not auto or manual["ts"] >= auto[0]):
            o["status"], o["status_origem"], o["status_ts"] = manual["status"], "manual", manual["ts"]
            o["status_motivo"] = "definido por você no painel"
        elif auto:
            o["status"], o["status_origem"], o["status_ts"], o["status_motivo"] = auto[1], "auto", auto[0], auto[2]
        else:
            o["status"], o["status_origem"], o["status_motivo"] = "aberto", "auto", None
        if o["status"] in ("a_caminho", "em_atendimento", "em_tratativa"):
            o["ciente"] = True  # alguém está cuidando: não repete o alarme
        if o["status"] == "em_tratativa" and o.get("confirmar"):
            base = max(o["ultima_ts"], o.get("status_ts") or 0)
            if time.time() - base < TRATATIVA_PERGUNTA:
                o.pop("confirmar", None)  # ficou para depois: pergunta só depois de 24 h


def _mesma_usina_oc(a, b):
    if a.get("chave_usina") and a.get("chave_usina") == b.get("chave_usina"):
        return True
    ca, cb = coletor.chave_codigo(a.get("codigo")), coletor.chave_codigo(b.get("codigo"))
    return bool(ca and ca == cb)


def normalizacao_posterior(h, d, vivas):
    """Ocorrência antiga ainda aberta (fora da janela, em tratativa): a usina foi normalizada depois do último aviso
    dela? Vale a mensagem de normalização da usina ou uma ocorrência nova da mesma usina que já foi normalizada,
    com as mesmas proteções de sempre (volta de comunicação ou de um inversor não fecha usina desarmada)."""
    critica = h.get("sev") == "critico"
    sobre = coletor.sem_acento((h.get("msg") or {}).get("texto") or "")
    de_comunicacao, de_inversor = bool(coletor.SO_COMUNICACAO.search(sobre)), "inversor" in sobre
    candidatos = []
    for n in d.get("normalizacoes") or []:
        if n["ts"] <= h["ultima_ts"] or not _mesma_usina_oc(h, n):
            continue
        # "comunicação restabelecida" só fecha o que era de comunicação; "inversor em operação", o que era de inversor
        if n.get("so_comunicacao") and (critica or not de_comunicacao):
            continue
        if n.get("so_inversor") and (critica or not de_inversor):
            continue
        candidatos.append(dict(n["msg"], ts=n["ts"]))
    for o in vivas:
        nz = o.get("normalizado")
        if not nz or nz.get("ts", 0) <= h["ultima_ts"] or not _mesma_usina_oc(h, o):
            continue
        if nz.get("motivo") in ("inatividade", "sem_registro") or (critica and o.get("sev") != "critico"):
            continue
        candidatos.append(dict(nz, motivo=nz.get("motivo") or "mensagem"))
    return min(candidatos, key=lambda x: x.get("ts", 0)) if candidatos else None


def ocorrencias_com_acoes(d, acoes):
    """Aplica 'ciente' e 'encerrar' do painel. Uma ocorrência encerrada à mão volta a abrir se chegar
    aviso novo da mesma usina depois do encerramento. O estado das usinas é recalculado em seguida."""
    # as marcações valem pelas MENSAGENS da ocorrência, não só pela identificação dela: se a ocorrência for
    # remontada (outra identificação), quem compartilha um aviso com a antiga herda o ciente/encerrar/reabrir
    por_msg = acoes_por_mensagem(acoes)
    agora = time.time()
    # ocorrências de usina ainda abertas que saíram da janela de 24 h: continuam no painel até você decidir
    # (CONTINUAR ACOMPANHANDO ou ENCERRAR); não entram se a mesma ocorrência já está ao vivo (remontada)
    vivas = d["ocorrencias"]
    ids_vivos = {i for o in vivas for i in (o.get("ids") or [])}
    chaves_vivas = {o["chave"] for o in vivas}
    usinas_abertas = {o["chave_usina"] for o in vivas if not o["normalizado"]}
    guardadas = []
    for k, h in relatorio._ler(relatorio.HIST, {}).items():
        if k in chaves_vivas or h.get("normalizado") or h.get("generico") or not indicadores.de_usina(h):
            continue
        if set(h.get("ids") or []) & ids_vivos:
            continue
        fim = normalizacao_posterior(h, d, vivas)
        if fim:
            guardadas.append(dict(h, normalizado=fim, fora_da_janela=True))  # resolvida depois: dá baixa (e o histórico guarda)
            continue
        if h.get("chave_usina") in usinas_abertas:
            continue  # a mesma usina tem ocorrência nova aberta: aparece só ela
        guardadas.append(dict(h, fora_da_janela=True))
    # remontada com a janela maior, uma ocorrência que o histórico já fechou (inatividade, sem registro, COG...)
    # continua fechada, a não ser que tenha chegado aviso novo depois do fechamento
    fechadas_hist = {}
    for h in relatorio._ler(relatorio.HIST, {}).values():
        if h.get("normalizado"):
            for i in h.get("ids") or []:
                fechadas_hist[i] = h["normalizado"]
    ocorrencias = []
    for o in vivas + guardadas:
        if not o.get("normalizado"):
            antigas = [fechadas_hist[i] for i in o.get("ids") or [] if i in fechadas_hist]
            ultima = max(antigas, key=lambda n: n.get("ts", 0)) if antigas else None
            if ultima and ultima.get("ts", 0) >= o["ultima_ts"]:
                o = dict(o, normalizado=ultima)
        herdadas = {}
        for mid in o.get("ids") or []:
            for tipo, a in por_msg.get(mid, {}).items():
                if tipo not in herdadas or a["ts"] > herdadas[tipo]["ts"]:
                    herdadas[tipo] = a
        o = dict(o, ciente=o["chave"] in acoes or "ciente" in herdadas, encerrada_manual=False)
        # "reabrir" desfaz uma baixa automática errada (ou por inatividade), até chegar uma normalização nova
        manter = acoes.get("keep:" + o["chave"]) or herdadas.get("keep")
        if manter and o["normalizado"] and o["normalizado"].get("ts", 0) <= manter["ts"]:
            o["normalizado"], o["reaberta"] = None, True
        enc = acoes.get("enc:" + o["chave"]) or herdadas.get("enc")
        if enc and not o["normalizado"] and o["ultima_ts"] <= enc["ts"]:
            o["normalizado"] = {"ts": enc["ts"], "de": "você", "motivo": "manual", "texto": "encerrada no painel" +
                                (f": {enc['nota']}" if enc.get("nota") else "")}
            o["encerrada_manual"] = True
        # sem novidade por 6 h: pergunta se continua (CONTINUAR ACOMPANHANDO adia a pergunta por mais 6 h)
        acomp = acoes.get("acomp:" + o["chave"]) or herdadas.get("acomp")
        base = max(o["ultima_ts"], acomp["ts"] if acomp else 0)
        o.pop("confirmar", None)
        if not o["normalizado"] and not o.get("generico") and agora - base >= coletor.INATIVIDADE:
            o["confirmar"] = {"desde": o["ultima_ts"], "acompanhando": bool(acomp)}
        ocorrencias.append(o)
    ocorrencias.sort(key=lambda o: (o["normalizado"] is not None, -o["ultima_ts"]))
    usinas = []
    for u in d["usinas"]:
        u = dict(u)
        oc = [o for o in ocorrencias if o["chave_usina"] == u["jid"]]
        if oc:
            abertas = [o for o in oc if not o["normalizado"]]
            u["abertas"] = len(abertas)
            u["estado"] = "critico" if any(o["sev"] == "critico" for o in abertas) else "alerta" if abertas else "normalizado"
        usinas.append(u)
    ordem = {"critico": 0, "alerta": 1, "normalizado": 2, "ativa": 3, "quieta": 4}
    usinas.sort(key=lambda u: (ordem[u["estado"]], -(u["ultima_ts"] or 0)))
    # código da usina (o mesmo do KMZ) para os grupos que o COG nunca citou com código: casa pelo nome aprendido
    conhecidos = [(c, coletor.assinatura(n)) for c, n in relatorio.codigos().items()]
    for u in usinas:
        if not u.get("codigo"):
            ass = coletor.assinatura(u["nome"])
            u["codigo"] = next((c for c, a in conhecidos if coletor.mesma_usina(ass, a)), None)
    por_jid = {u["jid"]: u.get("codigo") for u in usinas}
    for o in ocorrencias:
        if not o.get("codigo"):
            o["codigo"] = por_jid.get(o["chave_usina"])
    for lista in (d.get("atividades") or [], d.get("presencas") or []):
        for i in lista:
            if not i.get("codigo"):
                i["codigo"] = por_jid.get(i["chave_usina"]) or (i["chave_usina"] if re.fullmatch(r"[A-Z]{2,4}\d{3}", str(i["chave_usina"])) else None)
    return ocorrencias, usinas


def pontos_usinas():
    return [{"codigo": p["nome"], "lat": p["lat"], "lon": p["lon"]}
            for p in dados_mapa().get("pontos", []) if p.get("categoria") == "usina"]


def sincronizar_sempre():
    cache = estado["cache"]  # as conversas lidas ficam aqui; o detalhe da ocorrência mostra as mensagens delas
    while True:
        try:
            clima.atualizar_em_segundo_plano(pontos_usinas())  # a cada 30 min, sem segurar a sincronização
        except Exception:
            traceback.print_exc()
        estado["sincronizando"] = True
        try:
            dados = coletor.coletar(cache=cache, log=lambda s: print(time.strftime("%H:%M:%S"), s, flush=True))
            with trava:
                estado["dados"], estado["erro"] = dados, None
                painel = montar()
            registrar(painel)
        except Exception as e:
            estado["erro"] = f"sincronização falhou: {e}"
            traceback.print_exc()
        estado["sincronizando"] = False
        acordar.wait(INTERVALO)
        acordar.clear()


acordar = threading.Event()


def ler_token():
    """Senha do acesso remoto (celular pelo Tailscale). Criada na primeira vez, só neste PC."""
    caminho = os.path.join(DADOS, "token")
    try:
        with open(caminho, encoding="utf-8") as f:
            t = f.read().strip()
            if len(t) >= 24:
                return t
    except OSError:
        pass
    import secrets
    t = secrets.token_urlsafe(24)
    os.makedirs(DADOS, exist_ok=True)
    with open(os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(t)
    return t


TOKEN = ler_token()
TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
_mapa = {"mtime": None, "dados": None}


def dados_mapa():
    """Pontos e polígonos do KMZ das usinas (lido de novo só quando o arquivo muda)."""
    caminho = config.kmz()
    try:
        mt = os.path.getmtime(caminho)
    except OSError:
        return {"erro": "Sem KMZ das usinas: coloque o arquivo em " + caminho + " (ou indique o caminho em config.json, campo kmz)",
                "pontos": [], "areas": [], "codigos": relatorio.codigos()}
    preferir = config.carregar().get("kmz_preferir") or {}
    if _mapa["mtime"] != (mt, str(preferir)):
        d = mapa.ler_kmz(caminho)
        # o mesmo código em duas pastas: fica com o código o ponto da pasta preferida (config.json, kmz_preferir);
        # o outro vira "CAC100 (Blackout)" para não ser confundido
        usinas = [p for p in d["pontos"] if p["categoria"] == "usina"]
        for cod, pasta in preferir.items():
            iguais = [p for p in usinas if p["nome"].upper() == cod.upper()]
            if len(iguais) > 1:
                for p in iguais:
                    if p["grupo"].lower() != str(pasta).lower():
                        p["nome"] = f"{p['nome']} ({p['grupo']})"
        _mapa["dados"], _mapa["mtime"] = d, (mt, str(preferir))
    return dict(_mapa["dados"], codigos=relatorio.codigos())


def detalhe_ocorrencia(chave):
    """A ocorrência e a conversa dos grupos onde ela apareceu: de 30 min antes do primeiro aviso até
    30 min depois da normalização (ou até agora, se ainda está aberta)."""
    with trava:
        painel = montar()
    o = next((x for x in painel.get("ocorrencias", []) if x["chave"] == chave), None)
    if not o:
        o = relatorio._ler(relatorio.HIST, {}).get(chave)
    if not o:
        return 404, {"erro": "ocorrência não encontrada (pode ter saído da janela do painel)"}
    ini = o["inicio_ts"] - 1800
    fim = ((o.get("normalizado") or {}).get("ts") or time.time()) + 1800
    destaque = set(o.get("ids") or [o["msg"].get("id")])
    mensagens = []
    for jid in o.get("jids") or [o.get("jid")]:
        guardado = estado["cache"].get(jid) or {}
        dados = guardado.get("dados") or {}
        grupo = (dados.get("chat") or {}).get("name") or jid
        for m in dados.get("messages") or []:
            if ini <= m.get("ts", 0) <= fim:
                c = coletor.compacta(m)
                c["texto"] = coletor.texto(m)[:1500]
                c.update(grupo=grupo, aviso=m.get("id") in destaque,
                         normalizacao=bool(o.get("normalizado")) and m.get("id") == o["normalizado"].get("id"))
                mensagens.append(c)
    mensagens.sort(key=lambda m: m["ts"])
    if len(mensagens) > 200:  # conversa muito longa: fica o entorno dos avisos e o fim
        marcas = [i for i, m in enumerate(mensagens) if m["aviso"] or m["normalizacao"]]
        manter = {j for i in marcas for j in range(max(0, i - 8), min(len(mensagens), i + 12))} | set(range(len(mensagens) - 40, len(mensagens)))
        mensagens = [m for i, m in enumerate(mensagens) if i in manter]
    return 200, {"ocorrencia": o, "mensagens": mensagens}


STATUS_DIARIO = {"chamado": ("Resolvido", "Em andamento", "Pendente"),
                 "tarefa": ("Pendente", "Em andamento", "Concluída", "Cancelada")}


def diario_atualizar(corpo):
    """Muda o status (e acrescenta uma observação) de um chamado ou tarefa na planilha do Diário, pelo ID.
    Usa o próprio diario.py, que faz cópia de segurança antes de gravar e recusa se a planilha estiver aberta."""
    tipo, id_, status = corpo.get("tipo"), str(corpo.get("id") or ""), corpo.get("status")
    nota = str(corpo.get("nota") or "").strip()[:500]
    if tipo not in STATUS_DIARIO or not id_ or (status and status not in STATUS_DIARIO[tipo]) or not (status or nota):
        return 400, {"erro": "pedido inválido"}
    lista = (estado["dados"] or {}).get("chamados" if tipo == "chamado" else "tarefas") or []
    atual = next((l for l in lista if l.get("id") == id_), None)
    if not atual:
        return 404, {"erro": "não achei esse item no Diário (ele foi digitado à mão, sem ID?)"}
    item = {"id": id_, "_painel": True}
    if status:
        item["status"] = status
    if nota or status:
        campo = "descricao" if tipo == "chamado" else "andamento"
        registro = f"[{time.strftime('%d/%m %H:%M')} painel] " + (f"{status}. " if status else "") + nota
        item[campo] = ((atual.get(campo) or "").rstrip() + "\n" + registro).strip()
    import subprocess, tempfile
    py, script = config.diario()
    if not script:
        return 400, {"erro": "o Diário de Chamados não está configurado nesta instalação"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", dir=DADOS, delete=False, encoding="utf-8") as f:
        json.dump([item], f, ensure_ascii=False)
        arq = f.name
    try:
        r = subprocess.run([py, script, "chamados" if tipo == "chamado" else "tarefas", arq],
                           capture_output=True, text=True, timeout=90, encoding="utf-8")
    finally:
        os.unlink(arq)
    if r.returncode:
        return 409, {"erro": (r.stderr.strip().splitlines() or ["o Diário recusou a gravação"])[-1]}
    chamados, _ = coletor.diario("chamados")
    tarefas, _ = coletor.diario("tarefas")
    with trava:
        if estado["dados"]:
            estado["dados"]["chamados"], estado["dados"]["tarefas"] = chamados, tarefas
        return 200, montar()


def perfil():
    c = config.carregar()
    return {"nome": c.get("nome_usuario") or "", "organizacao": c.get("organizacao") or "",
            "diario": bool(config.diario()[1]), "versao": versao_local()}


def ler_silencio():
    """Horário sem som (config.json: silencio_inicio / silencio_fim, horas cheias). Padrão: 20h às 7h."""
    c = config.carregar()
    return {"inicio": int(c.get("silencio_inicio", 20)), "fim": int(c.get("silencio_fim", 7))}


def teste_alarme():
    """Ocorrência falsa, marcada como teste, para conferir se o celular toca (botão TESTAR ALARME do painel)."""
    t = estado.get("teste")
    if not t or time.time() - t > TESTE_DURA:
        return []
    return [{"chave": f"teste|{int(t)}", "sev": "critico", "usina": "TESTE DO ALARME",
             "texto": "Teste disparado no painel. Se tocou o alarme industrial, está tudo certo.", "inicio_ts": int(t), "ciente": True}]


APK_PADRAO = f"https://github.com/{config.REPOSITORIO}/releases/latest/download/CentroOperacoes.apk"
_release = {"quando": 0, "versao": 0, "app": 0, "apk": APK_PADRAO, "notas": ""}


def versao_local():
    """Versão desta instalação (arquivo VERSAO na raiz do projeto, o mesmo número da Release no GitHub)."""
    try:
        with open(os.path.join(PASTA, "VERSAO"), encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def ultima_release():
    """Última versão publicada no GitHub (consulta no máximo a cada 30 min; sem internet, fica a última conhecida)."""
    if time.time() - _release["quando"] < 1800:
        return _release
    _release["quando"] = time.time()
    try:
        import urllib.request
        req = urllib.request.Request(f"https://api.github.com/repos/{config.REPOSITORIO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "centro-operacoes"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
        _release["versao"] = int(str(d.get("tag_name", "v0")).lstrip("vV") or 0)
        corpo = d.get("body") or ""
        _release["notas"] = corpo.split("app-versao:")[0].strip()[:1500]
        m = re.search(r"app-versao:\s*(\d+)", corpo)  # a versão do APK (só muda quando o app Android muda)
        _release["app"] = int(m.group(1)) if m else _release["versao"]
        _release["apk"] = next((a["browser_download_url"] for a in d.get("assets", []) if a["name"].endswith(".apk")), APK_PADRAO)
    except Exception:
        pass
    return _release


def versoes():
    """tela: muda a cada edição do painel; pc: versão instalada aqui; ultima: a publicada no GitHub;
    app: versão do APK que o celular deve ter (a publicada, ou um APK gerado aqui mesmo mais novo)."""
    import hashlib
    with open(os.path.join(PASTA, "painel.html"), "rb") as f:
        tela = hashlib.sha1(f.read()).hexdigest()[:12]
    try:
        with open(os.path.join(PASTA, "dist", "versao.json"), encoding="utf-8") as f:
            local_apk = int(json.load(f).get("app", 0))
    except (OSError, ValueError):
        local_apk = 0
    rel = ultima_release()
    pc = versao_local()
    return {"tela": tela, "pc": pc, "ultima": rel["versao"], "pc_nova": rel["versao"] > pc, "notas": rel["notas"],
            "app": max(rel["app"], local_apk), "apk": rel["apk"]}


def ip_tailscale():
    import shutil, subprocess
    exe = shutil.which("tailscale")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5)
        return (r.stdout.split() or [None])[0]
    except Exception:
        return None


def pagina_parear(base, token):
    """Página que o celular abre ao escanear o QR do PC: baixa o app (se precisar) e conecta este celular."""
    import html as h, urllib.parse as up
    q = up.urlencode({"base": base, "t": token})
    apk = versoes()["apk"]
    intent = (f"intent://parear?{q}#Intent;scheme=centrooperacoes;package=com.mateus.centrooperacoes;"
              f"S.browser_fallback_url={up.quote(apk, safe='')};end")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conectar ao Centro de Operações</title><style>
body{{margin:0;background:#03060f;color:#e2e8f0;font:16px/1.5 system-ui,sans-serif;padding:28px 20px}}
h1{{font-size:20px;letter-spacing:1px;color:#dbeafe}} p{{color:#9fb0d4}}
a.b{{display:block;text-align:center;padding:16px;border-radius:12px;margin:14px 0;font-weight:700;letter-spacing:.5px;text-decoration:none}}
.p{{background:#0b2a1d;color:#3ee08a;border:1px solid #1e7a4c}} .s{{background:#0d1938;color:#56ccff;border:1px solid #2b4a99}}
small{{color:#7d8fb5}}</style></head><body>
<h1>◉ CENTRO DE OPERAÇÕES</h1>
<p>Este celular vai receber os alarmes do PC <b>{h.escape(base)}</b>.</p>
<a class="b p" href="{h.escape(intent)}">CONECTAR ESTE CELULAR</a>
<p><small>Ainda não tem o app? Baixe e instale primeiro (só Android), depois volte e toque em Conectar:</small></p>
<a class="b s" href="{h.escape(apk)}">BAIXAR O APP (APK)</a>
<p><small>O celular precisa estar no mesmo Tailscale do PC. Não compartilhe este QR: ele dá acesso ao seu painel.</small></p>
</body></html>"""


def atualizar_pc():
    """git pull e reinício do servidor (só pelo próprio PC). O reinício é feito trocando o processo por um novo."""
    import subprocess, threading
    r = subprocess.run(["git", "-C", PASTA, "pull", "--ff-only"], capture_output=True, text=True, timeout=120)
    saida = (r.stdout + r.stderr).strip()[-800:]
    if r.returncode:
        return 409, {"erro": "não consegui atualizar: " + saida}
    _release["quando"] = 0
    threading.Timer(1.5, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)).start()
    return 200, {"ok": True, "saida": saida}


class Pagina(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---------- quem pode entrar ----------
    def token_ok(self):
        h = self.headers.get("Authorization", "")
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("t", [""])[0]
        return hmac.compare_digest(h, "Bearer " + TOKEN) or (q and hmac.compare_digest(q, TOKEN))

    def permitido(self):
        ip = ipaddress.ip_address(self.client_address[0])
        if ip.is_loopback:
            return True
        return ip in TAILSCALE and self.token_ok()  # celular e outros aparelhos do Tailscale, só com a senha

    def responder(self, codigo, corpo, tipo="application/json; charset=utf-8", cache=False):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        if self.token_ok():  # o app do celular lê de outra origem; só libera para quem tem a senha
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        if not self.permitido():
            return self.responder(403, {"erro": "acesso negado"})
        url = urllib.parse.urlsplit(self.path)
        caminho, q = url.path, urllib.parse.parse_qs(url.query)
        if caminho == "/api/versao":
            return self.responder(200, versoes())
        if caminho in ("/", "/index.html", "/painel.html"):
            with open(os.path.join(PASTA, "painel.html"), "rb") as f:
                pagina = f.read()
            marca = f'<meta name="versao-tela" content="{versoes()["tela"]}">'.encode()
            return self.responder(200, pagina.replace(b"<head>", b"<head>" + marca, 1), "text/html; charset=utf-8")
        if caminho == "/api/indicadores":
            try:
                dias = max(1, min(45, int(q.get("dias", ["7"])[0])))
            except ValueError:
                dias = 7
            with trava:
                painel = montar()
                d = estado["dados"] or {}
                base = {"ocorrencias": painel.get("ocorrencias", []), "chamados": d.get("chamados", []),
                        "tarefas": d.get("tarefas", []), "atividades": d.get("atividades", [])}
            if not painel.get("pronto"):
                return self.responder(200, {"pronto": False})
            return self.responder(200, indicadores.calcular(dias, q.get("cliente", [""])[0], base, dados_mapa()))
        if caminho == "/api/clima":
            return self.responder(200, clima.mapa())
        if caminho == "/api/clima/painel":
            return self.responder(200, clima.painel())
        if caminho == "/api/ocorrencia":
            return self.responder(*detalhe_ocorrencia(q.get("chave", [""])[0]))
        if caminho in ("/manifest.webmanifest", "/sw.js", "/icone-192.png", "/icone-512.png", "/icone.svg"):
            tipos = {".webmanifest": "application/manifest+json", ".js": "application/javascript", ".png": "image/png", ".svg": "image/svg+xml"}
            with open(os.path.join(PASTA, "pwa", caminho.lstrip("/")), "rb") as f:
                return self.responder(200, f.read(), tipos[os.path.splitext(caminho)[1]])
        if caminho == "/parear":
            ip = ip_tailscale()
            base = f"http://{ip}:{PORTA}" if ip else f"http://{self.headers.get('Host')}"
            return self.responder(200, pagina_parear(base, TOKEN).encode(), "text/html; charset=utf-8")
        if caminho == "/api/pareamento":
            # só no próprio PC: devolve o link (com a senha) que vira o QR de sincronização do celular
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                return self.responder(403, {"erro": "só no PC"})
            ip = ip_tailscale()
            return self.responder(200, {"ip": ip, "url": f"http://{ip}:{PORTA}/parear?t={TOKEN}" if ip else None,
                                        "apk": versoes()["apk"]})
        if caminho == "/app.apk":  # o celular baixa daqui a versão nova: o APK gerado neste PC ou o publicado no GitHub
            apk = os.path.join(PASTA, "dist", "CentroOperacoes.apk")
            v = versoes()
            if not os.path.isfile(apk) or v["app"] > (json.load(open(os.path.join(PASTA, "dist", "versao.json"))).get("app", 0)
                                                      if os.path.isfile(os.path.join(PASTA, "dist", "versao.json")) else 0):
                self.send_response(302)
                self.send_header("Location", v["apk"])
                self.end_headers()
                return
            with open(apk, "rb") as f:
                corpo = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Disposition", f'attachment; filename="CentroOperacoes-v{versoes()["app"]}.apk"')
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return
        if caminho.startswith("/vendor/"):
            alvo = os.path.normpath(os.path.join(PASTA, caminho.lstrip("/")))
            if not alvo.startswith(os.path.join(PASTA, "vendor") + os.sep) or not os.path.isfile(alvo):
                return self.responder(404, {"erro": "não encontrado"})
            tipo = mimetypes.guess_type(alvo)[0] or "application/octet-stream"
            with open(alvo, "rb") as f:
                return self.responder(200, f.read(), tipo, cache=True)
        if caminho == "/api/dados":
            with trava:
                return self.responder(200, montar())
        if caminho == "/api/mapa":
            return self.responder(200, dados_mapa())
        if caminho == "/api/alertas":
            # resumo leve para o serviço de notificações do celular (consulta a cada minuto)
            with trava:
                p = montar()
            if not p.get("pronto"):
                return self.responder(200, {"pronto": False})
            return self.responder(200, {
                "pronto": True, "quando": p["quando"], "whatsapp": (p.get("whatsapp") or {}).get("conexao"),
                "app_versao": versoes()["app"], "silencio": ler_silencio(),
                "plantao": (p.get("plantao") or {}).get("ativo"),
                "ocorrencias": [{"chave": o["chave"], "usina": o["usina"], "inicio_ts": o["inicio_ts"], "ciente": o["ciente"],
                                 "sev": "alerta" if (o.get("durante_manutencao") or {}).get("ate_agora") else o["sev"],
                                 "texto": (f"🔧 durante manutenção ({o['durante_manutencao']['descricao']}): "
                                           if (o.get("durante_manutencao") or {}).get("ate_agora") else "") + o["msg"]["texto"][:200]}
                                for o in p["ocorrencias"] if not o["normalizado"] and not o.get("generico")]
                               + teste_alarme(),
                "confirmar": [{"chave": o["chave"], "usina": o["usina"], "desde": o["confirmar"]["desde"]}
                              for o in p["ocorrencias"] if o.get("confirmar") and not o["normalizado"]],
                "painel": resumo_celular(p),
                "marcacoes": [{"chave": a["chave"], "nome": a["nome"], "desde_ts": a["desde_ts"],
                               "texto": (a["previa"][0] if a["previa"] else {}).get("texto", "")[:200]}
                              for a in p["aguardando"] if a.get("motivo") == "marcou você"],
            })
        if caminho == "/config.js":  # no app Android este arquivo traz o endereço do PC e a senha; aqui fica vazio
            return self.responder(200, b"", "application/javascript")
        if caminho == "/relatorio":
            plantao = ler_plantao()
            fim = float(q["fim"][0]) if "fim" in q else time.time()
            inicio = float(q["inicio"][0]) if "inicio" in q else plantao["inicio_ts"] if plantao["ativo"] else fim - 86400
            with trava:
                painel = montar()
            pagina, _ = relatorio.montar(inicio, fim, painel, plantao)
            return self.responder(200, pagina.encode(), "text/html; charset=utf-8")
        self.responder(404, {"erro": "não encontrado"})

    def do_POST(self):
        if not self.permitido():
            return self.responder(403, {"erro": "acesso negado"})
        # no PC, sem a senha, só aceita pedidos da própria página (nunca de outro site aberto no navegador)
        origem = self.headers.get("Origin", "")
        if not self.token_ok() and origem and origem not in (f"http://127.0.0.1:{PORTA}", f"http://localhost:{PORTA}"):
            return self.responder(403, {"erro": "origem não permitida"})
        try:
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        except ValueError:
            return self.responder(400, {"erro": "json inválido"})
        if self.path == "/api/sincronizar":
            acordar.set()
            return self.responder(200, {"ok": True})
        if self.path == "/api/atualizar":
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                return self.responder(403, {"erro": "a atualização só pode ser feita no próprio PC"})
            return self.responder(*atualizar_pc())
        if self.path == "/api/teste-alerta":
            estado["teste"] = time.time()
            return self.responder(200, {"ok": True, "dura_seg": TESTE_DURA})
        if self.path == "/api/diario":
            return self.responder(*diario_atualizar(corpo))
        if self.path == "/api/plantao":
            with trava:
                if corpo.get("acao") == "iniciar":
                    equipe = corpo.get("equipe") or []
                    if isinstance(equipe, str):
                        equipe = [e.strip() for e in equipe.split(",") if e.strip()]
                    plantao_iniciar(str(corpo.get("titulo") or "")[:80], [str(e)[:40] for e in equipe][:10])
                    return self.responder(200, montar())
                if corpo.get("acao") == "finalizar":
                    painel = montar()
                    if painel.get("pronto"):
                        relatorio.registrar(painel["ocorrencias"], estado["dados"].get("codigos"))
                        relatorio.registrar_manutencoes(painel.get("atividades") or [], painel.get("presencas") or [])
                    item = plantao_finalizar(painel)
                    if not item:
                        return self.responder(400, {"erro": "não há plantão ativo"})
                    return self.responder(200, dict(montar(), finalizado=item))
            return self.responder(400, {"erro": "ação de plantão inválida"})
        if self.path == "/api/acao":
            chave, tipo = corpo.get("chave"), corpo.get("tipo")
            if not chave or tipo not in ("respondi", "resolvido", "ignorar", "lembrar", "desfazer", "ciente", "encerrar", "reabrir", "acompanhar", "status",
                                                  "fim_manutencao", "continua_manutencao", "reabrir_manutencao", "saida_tecnico"):
                return self.responder(400, {"erro": "ação inválida"})
            with trava:
                acoes = ler_acoes()
                atual = next((o for o in (estado["dados"] or {}).get("ocorrencias", []) if o["chave"] == chave), None) \
                    or relatorio._ler(relatorio.HIST, {}).get(chave)
                ids = (atual or {}).get("ids") or []
                if tipo == "desfazer":
                    acoes.pop(chave, None)
                elif tipo == "reabrir":
                    acoes.pop("enc:" + chave, None)
                    acoes["keep:" + chave] = {"tipo": "reabrir", "ts": int(time.time()), "ids": ids}
                elif tipo == "fim_manutencao":
                    acoes["fimatv:" + chave] = {"tipo": tipo, "ts": int(time.time()), "nota": str(corpo.get("nota", ""))[:200]}
                elif tipo == "continua_manutencao":
                    acoes["contatv:" + chave] = {"tipo": tipo, "ts": int(time.time())}
                elif tipo == "reabrir_manutencao":
                    acoes.pop("fimatv:" + chave, None)
                    hist = relatorio._ler(relatorio.MANUT, {})  # a cópia guardada também volta a "em andamento"
                    if chave in hist and hist[chave].get("manual"):
                        hist[chave].update(status="andamento", fim_ts=None, fim_msg=None, manual=False)
                        relatorio._gravar(relatorio.MANUT, hist)
                elif tipo == "saida_tecnico":
                    acoes["saida:" + chave] = {"tipo": tipo, "ts": int(time.time())}
                elif tipo == "acompanhar":
                    acoes["acomp:" + chave] = {"tipo": "acompanhar", "ts": int(time.time()), "ids": ids}
                elif tipo == "status":
                    st = corpo.get("status")
                    if st not in STATUS:
                        return self.responder(400, {"erro": "status inválido"})
                    if st in ("resolvido", "resolvido_cog"):
                        nota = str(corpo.get("nota", ""))[:200] or ("resolvido pelo COG" if st == "resolvido_cog" else "")
                        if not (atual or {}).get("normalizado"):
                            acoes["enc:" + chave] = {"tipo": "encerrar", "ts": int(time.time()), "nota": nota, "ids": ids}
                        acoes["st:" + chave] = {"tipo": "status", "status": st, "ts": int(time.time()), "ids": ids}
                    else:
                        if (atual or {}).get("normalizado") or ("enc:" + chave) in acoes:
                            acoes.pop("enc:" + chave, None)  # voltar de "resolvido" reabre a ocorrência
                            acoes["keep:" + chave] = {"tipo": "reabrir", "ts": int(time.time()), "ids": ids}
                        acoes["st:" + chave] = {"tipo": "status", "status": st, "ts": int(time.time()), "ids": ids}
                elif tipo == "encerrar":
                    acoes["enc:" + chave] = {"tipo": "encerrar", "ts": int(time.time()), "nota": str(corpo.get("nota", ""))[:200], "ids": ids}
                else:
                    a = {"tipo": tipo, "ts": int(time.time()), "nome": corpo.get("nome", ""),
                         "tipo_chat": corpo.get("tipo_chat", "")}
                    if tipo == "lembrar":
                        a["ate"] = int(time.time() + 60 * max(5, min(int(corpo.get("minutos", 60)), 7 * 1440)))
                    if ids:
                        a["ids"] = ids
                    acoes[chave] = a
                # limpa marcações velhas (mais de 7 dias)
                acoes = {k: v for k, v in acoes.items()
                         if time.time() - v["ts"] < (90 if k.startswith(("st:", "enc:", "keep:", "acomp:")) else 7) * 86400}
                gravar_acoes(acoes)
                painel = montar()
                registrar(painel)
                return self.responder(200, painel)
        self.responder(404, {"erro": "não encontrado"})


class Servidor(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # navegador que fechou a conexão no meio da resposta (troca de página, celular sem sinal): não é erro do painel
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def registrar(painel):
    """Histórico de ocorrências e, quando o plantão termina, a passagem de plantão salva em Documentos."""
    if not painel.get("pronto"):
        return
    try:
        relatorio.registrar(painel["ocorrencias"], estado["dados"].get("codigos"))
        relatorio.registrar_manutencoes(painel.get("atividades") or [], painel.get("presencas") or [])
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    threading.Thread(target=sincronizar_sempre, daemon=True).start()
    # 0.0.0.0 para o celular chegar pelo Tailscale; quem não é deste PC nem do Tailscale com a senha é recusado
    for tentativa in range(20):
        try:
            servidor = Servidor(("0.0.0.0", PORTA), Pagina)
            break
        except OSError:
            time.sleep(1)
    else:
        raise SystemExit(f"a porta {PORTA} está ocupada")
    print(f"Centro de Operações em http://127.0.0.1:{PORTA} (e pelo Tailscale, com a senha)", flush=True)
    servidor.serve_forever()
