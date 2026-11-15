# Histórico de ocorrências (30 dias) e relatório de passagem de plantão do Centro de Operações.
import datetime as dt, html, json, os, re, time

import config
DADOS = config.DADOS
HIST = os.path.join(DADOS, "ocorrencias.json")
CODIGOS = os.path.join(DADOS, "codigos.json")

GUARDAR = 45 * 86400  # o histórico importado cobre 30 dias; guarda um pouco mais


def _ler(caminho, padrao):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _gravar(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def registrar(ocorrencias, codigos):
    """Junta as ocorrências da coleta atual ao histórico (a versão mais nova de cada uma vale)."""
    hist = _ler(HIST, {})
    # o que ainda está na janela da coleta (24 h) é refeito a cada vez: se o painel juntou duas ocorrências
    # (ex.: grupo e código da mesma usina), a versão separada antiga sai do histórico
    janela = time.time() - 24 * 3600 + 600
    atuais = {o["chave"] for o in ocorrencias}
    hist = {k: v for k, v in hist.items() if k in atuais or v.get("inicio_ts", 0) < janela}
    for o in ocorrencias:
        hist[o["chave"]] = o
    # saiu da janela ainda aberta: continua aberta (o painel pergunta se segue). Só sai a cópia que foi
    # remontada com outra identificação (as mesmas mensagens estão numa ocorrência atual)
    ids_atuais = {i for o in ocorrencias for i in (o.get("ids") or [])}
    for k in [k for k, v in hist.items() if k not in atuais and not v.get("normalizado")
              and set(v.get("ids") or []) & ids_atuais]:
        del hist[k]
    limite = time.time() - GUARDAR
    hist = {k: v for k, v in hist.items() if v.get("ultima_ts", 0) >= limite}
    _gravar(HIST, hist)
    if codigos:
        atuais = _ler(CODIGOS, {})
        if any(atuais.get(k) != v for k, v in codigos.items()):
            atuais.update(codigos)
            _gravar(CODIGOS, atuais)
    return hist


MANUT = os.path.join(DADOS, "manutencoes.json")
VISITAS = os.path.join(DADOS, "visitas.json")


def registrar_manutencoes(atividades, presencas):
    """Guarda atividades e visitas (entrada/saída) para o relatório de plantão e os indicadores (45 dias)."""
    limite = time.time() - GUARDAR
    janela = time.time() - 24 * 3600 + 600
    for arq, itens, ts in ((MANUT, atividades, "inicio_ts"), (VISITAS, presencas, "entrada_ts")):
        hist = _ler(arq, {})
        atuais = {i["chave"] for i in itens}
        hist = {k: v for k, v in hist.items() if (k in atuais or v.get(ts, 0) < janela) and v.get(ts, 0) >= limite}
        for i in itens:
            hist[i["chave"]] = i
        _gravar(arq, hist)


def manutencoes_periodo(inicio_ts, fim_ts):
    atv = [a for a in _ler(MANUT, {}).values() if a["inicio_ts"] <= fim_ts and (a.get("fim_ts") or time.time()) >= inicio_ts]
    vis = [v for v in _ler(VISITAS, {}).values() if v["entrada_ts"] <= fim_ts and (v.get("saida_ts") or time.time()) >= inicio_ts]
    return sorted(atv, key=lambda a: a["inicio_ts"]), sorted(vis, key=lambda v: v["entrada_ts"])


def codigos():
    return _ler(CODIGOS, {})


def historico(inicio_ts, fim_ts):
    """Ocorrências de usina que estiveram abertas em algum momento do período (conversa solta de grupo geral fica de fora)."""
    import indicadores
    out = []
    for o in _ler(HIST, {}).values():
        if not indicadores.de_usina(o):
            continue
        fim_o = (o.get("normalizado") or {}).get("ts") or time.time()
        if o["inicio_ts"] <= fim_ts and fim_o >= inicio_ts:
            out.append(o)
    return sorted(out, key=lambda o: o["inicio_ts"])


def _dur(seg):
    seg = max(0, int(seg))
    if seg < 3600:
        return f"{seg // 60} min"
    if seg < 86400:
        return f"{seg // 3600} h {seg % 3600 // 60:02d}"
    return f"{seg // 86400} d {seg % 86400 // 3600} h"


def _hora(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def montar(inicio_ts, fim_ts, painel, plantao=None):
    """Devolve (html, texto). `painel` é o que o servidor monta para a página (aguardando, chamados...)."""
    ocs = historico(inicio_ts, fim_ts)
    agora = time.time()
    fechadas = [o for o in ocs if o.get("normalizado") and o["normalizado"]["ts"] <= fim_ts]
    abertas = [o for o in ocs if o not in fechadas]
    criticas = [o for o in ocs if o["sev"] == "critico"]
    # mediana só das normalizações confirmadas (COG, mensagem ou você), como nos indicadores
    tempos = sorted(o["normalizado"]["ts"] - o["inicio_ts"] for o in fechadas
                    if o["normalizado"].get("motivo", "mensagem") in ("cog", "mensagem", "manual"))
    medio = _dur(tempos[len(tempos) // 2]) if tempos else "—"
    por_usina = {}
    for o in ocs:
        por_usina[o["usina"]] = por_usina.get(o["usina"], 0) + 1
    top = sorted(por_usina.items(), key=lambda x: -x[1])[:8]
    aguardando = [p for p in painel.get("aguardando", []) if not p.get("fechamento")]
    chamados = [c for c in painel.get("chamados", [])
                if (c.get("data") or "") >= dt.datetime.fromtimestamp(inicio_ts).strftime("%Y-%m-%d")]
    titulo = (plantao or {}).get("titulo") or "Passagem de plantão"
    equipe = ", ".join((plantao or {}).get("equipe") or [])
    periodo = f"{_hora(inicio_ts)} → {_hora(min(fim_ts, agora))}"

    # ---- texto para colar no WhatsApp / e-mail ----
    t = [f"*{titulo} — passagem de plantão*", f"Período: {periodo}" + (f" · Equipe: {equipe}" if equipe else ""), "",
         f"*Resumo:* {len(ocs)} ocorrências ({len(criticas)} críticas) · {len(fechadas)} normalizadas · "
         f"{len(abertas)} ainda abertas · tempo até normalizar (mediana): {medio}", ""]
    if abertas:
        t.append("*⚠️ Ainda abertas:*")
        for o in abertas:
            t.append(f"• {o['usina']} ({'CRÍTICA' if o['sev'] == 'critico' else 'alerta'}{', ' + STATUS_TXT[o['status']] if o.get('status') in STATUS_TXT else ''}) desde {_hora(o['inicio_ts'])}"
                     f"{' [herdada]' if o['inicio_ts'] < inicio_ts else ''}: {o['msg']['texto'][:140]}"
                     + (f" [{_clima(o)['rotulo']}]" if _clima(o) and _clima(o).get("nivel") else ""))
        t.append("")
    if fechadas:
        t.append("*✅ Normalizadas no período:*")
        for o in fechadas:
            t.append(f"• {o['usina']}: {_hora(o['inicio_ts'])} → {_hora(o['normalizado']['ts'])} "
                     f"({_dur(o['normalizado']['ts'] - o['inicio_ts'])})" + ({"manual": " [encerrada no painel]", "inatividade": " [baixa por inatividade, sem confirmação]"}.get((o.get("normalizado") or {}).get("motivo"), "")))
        t.append("")
    atv, vis = manutencoes_periodo(inicio_ts, fim_ts)
    if atv:
        t.append("*🔧 Manutenções no período:*")
        nomes_st = {"andamento": "em andamento", "concluida": "concluída", "cancelada": "cancelada", "sem_termino": "sem registro de término"}
        for a in atv:
            t.append(f"• {a['usina']}: {a['descricao']} ({nomes_st.get(a['status'], a['status'])}, {_hora(a['inicio_ts'])}"
                     + (f" → {_hora(a['fim_ts'])}" if a.get("fim_ts") and a["status"] != "andamento" else "") + ")")
        t.append("")
    if vis:
        t.append(f"*👷 Visitas a usinas:* {len(vis)}")
        for v in vis[:25]:
            fim_v = v.get("saida_ts")
            t.append(f"• {v['tecnico']} em {v['usina']}: {_hora(v['entrada_ts'])}" + (f" → {_hora(fim_v)}" if fim_v else " (ainda lá)"))
        t.append("")
    if aguardando:
        t.append("*💬 Conversas aguardando resposta:*")
        for p in aguardando:
            t.append(f"• {p['nome']} — há {_dur(agora - p['desde_ts'])}")
        t.append("")
    try:
        import clima
        av = [x for x in clima.resumo()["avisos"] if clima._em_vigor(x)]
    except Exception:
        av = []
    if av:
        t.append("*⚠️ Avisos do INMET em vigor:*")
        for x in av:
            t.append(f"• {x['descricao']} ({x['severidade']}, até {str(x['fim'])[11:16]}): {len(x['usinas'])} usinas na área")
        t.append("")
    if chamados:
        t.append("*📋 Chamados abertos no período:*")
        for c in chamados:
            t.append(f"• {c.get('usina')}: {c.get('assunto')} ({c.get('status')})")
    texto = "\n".join(t).strip()

    diario = episodios_diario(ocs, inicio_ts)
    # ---- página para imprimir / salvar em PDF ----
    e = html.escape
    def linha(o):
        fim = o.get("normalizado")
        estado = (f"normalizada {_hora(fim['ts'])}" + {"manual": " (no painel)", "inatividade": " (por inatividade)"}.get(fim.get("motivo"), "")) if fim and fim["ts"] <= fim_ts else "ABERTA"
        if estado == "ABERTA" and o.get("status") in STATUS_TXT:
            estado += " · " + STATUS_TXT[o["status"]]
        dur = _dur((fim["ts"] if fim and fim["ts"] <= fim_ts else min(agora, fim_ts)) - o["inicio_ts"])
        return (f"<tr class='{o['sev']}{' aberta' if estado.startswith('ABERTA') else ''}'><td>{e(_hora(o['inicio_ts']))}</td><td><b>{e(o['usina'])}</b>{'<div class=q>herdada do turno anterior</div>' if o['inicio_ts'] < inicio_ts else ''}</td>"
                f"<td>{'Crítica' if o['sev'] == 'critico' else 'Alerta'}</td><td>{e(o['msg']['texto'][:220])}<div class='q'>{e(o['msg']['de'])} · {e(' · '.join(o.get('grupos', [])))}</div>"
                f"{('<div class=q>Tempo na usina: ' + e(_clima(o)['rotulo']) + '</div>') if _clima(o) and _clima(o).get('nivel') else ''}</td>"
                f"<td>{e(estado)}</td><td>{dur}</td></tr>")
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Passagem de plantão {e(periodo)}</title><style>
body{{font:13px/1.45 system-ui,Segoe UI,Roboto,sans-serif;margin:24px;color:#111;background:#fff}}
h1{{font-size:20px;margin:0}} .sub{{color:#555;margin:4px 0 16px}}
.kpis{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}} .k{{border:1px solid #ddd;border-radius:8px;padding:8px 12px;min-width:120px}}
.k b{{display:block;font-size:22px}} .k span{{font-size:11px;color:#555;text-transform:uppercase;letter-spacing:.5px}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px}} th,td{{border-bottom:1px solid #e5e5e5;padding:6px;text-align:left;vertical-align:top}}
th{{font-size:11px;text-transform:uppercase;color:#555}} tr.critico td:nth-child(3){{color:#c1121f;font-weight:700}} tr.aberta td:nth-child(5){{color:#c1121f;font-weight:700}}
.q{{color:#666;font-size:11px}} h2{{font-size:14px;margin:18px 0 6px}} pre{{white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:8px;font-size:12px}}
.barra{{display:flex;gap:8px;margin-bottom:14px}}
.tl{{margin:6px 0 18px}} .tl .l{{display:grid;grid-template-columns:200px 1fr;gap:8px;align-items:center;height:16px}}
.tl .n{{font-size:11px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tl .t{{position:relative;height:100%;background:repeating-linear-gradient(90deg,#f1f1f1 0 1px,transparent 1px 12.5%)}}
.tl .b{{position:absolute;top:4px;height:8px;border-radius:4px;min-width:4px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.tl .eixo{{display:flex;justify-content:space-between;margin-left:208px;font-size:10px;color:#666}}
.tl .leg{{font-size:11px;color:#555;margin-bottom:4px}} .tl .leg i{{display:inline-block;width:10px;height:6px;border-radius:3px;margin:0 4px 0 10px}} button{{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #bbb;background:#f3f3f3;cursor:pointer}}
table.diario td,table.diario th{{font-size:11px}} h2.diario-t button{{font-size:12px;margin-left:8px}}
@media print{{.barra,pre,h2.texto,.diario-t button{{display:none}} body{{margin:8mm}}}}
</style></head><body>
<div class="barra"><button onclick="print()">Imprimir / salvar PDF</button><button onclick="navigator.clipboard.writeText(document.getElementById('txt').textContent).then(()=>this.textContent='Copiado ✓')">Copiar texto para WhatsApp</button></div>
<h1>{e(titulo)} — passagem de plantão</h1><div class="sub">Período {e(periodo)}{(' · Equipe: ' + e(equipe)) if equipe else ''} · gerado {e(_hora(agora))}</div>
<div class="kpis"><div class="k"><b>{len(ocs)}</b><span>ocorrências</span></div><div class="k"><b>{len(criticas)}</b><span>críticas</span></div>
<div class="k"><b>{len(fechadas)}</b><span>normalizadas</span></div><div class="k"><b>{len(abertas)}</b><span>ainda abertas</span></div>
<div class="k"><b>{medio}</b><span>tempo até normalizar (mediana)</span></div></div>
{linha_do_tempo(ocs, inicio_ts, min(fim_ts, agora))}
<h2>Ocorrências do período</h2><table><tr><th>Início</th><th>Usina</th><th>Nível</th><th>O que aconteceu</th><th>Situação</th><th>Duração</th></tr>
{''.join(linha(o) for o in ocs) or '<tr><td colspan=6>Nenhuma ocorrência registrada.</td></tr>'}</table>
<h2 class="diario-t">Diário de Bordo · para colar na planilha <button onclick="copiarDiario(this)">Copiar tabela</button></h2>
<div class="q diario-t">Mesmas colunas do Diário de Bordo do sobreaviso. Confira e complete Responsável, Formalizado e e-mail antes de colar. Status sugerido pelo andamento nos grupos.</div>
<table class="diario"><tr>{''.join(f"<th>{e(c)}</th>" for c in DIARIO_COLUNAS)}</tr>
{''.join("<tr>" + "".join(f"<td>{e(x)}</td>" for x in linha_diario(o, i + 1)) + "</tr>" for i, o in enumerate(diario)) or '<tr><td colspan=10>Nenhuma ocorrência.</td></tr>'}</table>
<pre id="diario-tsv" hidden>{e(chr(10).join(chr(9).join(x.replace(chr(10), " ") for x in linha_diario(o, i + 1)) for i, o in enumerate(diario)))}</pre>
<script>function copiarDiario(b){{navigator.clipboard.writeText(document.getElementById('diario-tsv').textContent).then(()=>b.textContent='Copiado ✓ (cole na coluna Nº da planilha)')}}</script>
<h2>Manutenções no período</h2><table><tr><th>Início</th><th>Usina</th><th>Atividade</th><th>Situação</th></tr>
{''.join(f"<tr><td>{e(_hora(a['inicio_ts']))}</td><td>{e(a['usina'])}</td><td>{e(a['descricao'])}</td><td>{e({'andamento': 'em andamento', 'concluida': 'concluída ' + (_hora(a['fim_ts']) if a.get('fim_ts') else ''), 'cancelada': 'cancelada', 'sem_termino': 'sem registro de término'}.get(a['status'], a['status']))}</td></tr>" for a in atv) or '<tr><td colspan=4>Nenhuma registrada pelo COG.</td></tr>'}</table>
<h2>Visitas a usinas (entrada e saída dos técnicos)</h2><table><tr><th>Técnico</th><th>Usina</th><th>Entrada</th><th>Saída</th><th>Tempo</th></tr>
{''.join(f"<tr><td>{e(v['tecnico'])}</td><td>{e(v['usina'])}</td><td>{e(_hora(v['entrada_ts']))}</td><td>{e(_hora(v['saida_ts'])) if v.get('saida_ts') and not v.get('sem_saida') else ('sem registro' if v.get('sem_saida') else 'ainda lá')}</td><td>{_dur((v.get('saida_ts') or agora) - v['entrada_ts'])}</td></tr>" for v in vis) or '<tr><td colspan=5>Nenhuma registrada.</td></tr>'}</table>
<h2>Usinas com mais ocorrências</h2><table><tr><th>Usina</th><th>Ocorrências</th></tr>{''.join(f'<tr><td>{e(u)}</td><td>{n}</td></tr>' for u, n in top) or '<tr><td colspan=2>—</td></tr>'}</table>
<h2>Conversas aguardando resposta</h2><table><tr><th>Conversa</th><th>Esperando há</th><th>Última mensagem</th></tr>
{''.join(f"<tr><td>{e(p['nome'])}</td><td>{_dur(agora - p['desde_ts'])}</td><td>{e((p['previa'] or [{}])[-1].get('texto', ''))[:160]}</td></tr>" for p in aguardando) or '<tr><td colspan=3>Nenhuma.</td></tr>'}</table>
<h2>Chamados abertos no período (Diário)</h2><table><tr><th>Data</th><th>Usina</th><th>Assunto</th><th>Status</th></tr>
{''.join(f"<tr><td>{e(c.get('data',''))} {e(c.get('hora',''))}</td><td>{e(c.get('usina',''))}</td><td>{e(c.get('assunto',''))}</td><td>{e(c.get('status',''))}</td></tr>" for c in chamados) or '<tr><td colspan=4>Nenhum.</td></tr>'}</table>
<h2 class="texto">Texto para WhatsApp / e-mail</h2><pre id="txt">{e(texto)}</pre>
</body></html>"""
    return pagina, texto


STATUS_TXT = {"aberto": "em aberto", "a_caminho": "técnico a caminho", "em_atendimento": "em atendimento",
              "em_tratativa": "em tratativa"}


# ---- Diário de Bordo do sobreaviso: as mesmas colunas da planilha, para copiar e colar ----
DIARIO_COLUNAS = ["Nº", "PROJETO / UFV", "O QUE HOUVE?", "TRATATIVAS REALIZADAS", "FORMALIZADO?", "E-MAIL DE FORMALIZAÇÃO",
                  "TRATATIVAS A SEREM TOMADAS", "RESPONSÁVEL", "STATUS", "OS / EVIDÊNCIAS"]
_EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2190-\u2BFF\uFE0F\u200d]")


def _limpo(t, n=200):
    t = _EMOJI.sub(" ", str(t or "")).replace("*", " ").replace("_", " ").replace(">", " ").replace("\t", " ")
    t = " ".join(t.split()).strip(" -–·:")
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def _o_que_houve(o):
    t = (o.get("msg") or {}).get("texto") or ""
    m = re.search(r"Descri[çc][ãa]o:\s*(.+?)(?:👷|T[ée]cnico acionado|Nossa equipe|Favor confirmar|Manteremos|$)", t)
    if m:
        return _limpo(m.group(1), 180)
    m = re.search(r"Ocorr[êe]ncia:\s*([^*>]+)", t)
    if m:
        resto = re.sub(r"^.*?Ocorr[êe]ncia:\s*[^*>]+\*?", "", t, count=1)
        return _limpo(m.group(1) + (" · " + resto if resto.strip() else ""), 180)
    return _limpo(re.sub(r"^\s*\*?\s*\*?UFV [^*]+\*", "", t), 180)


def _status_diario(o):
    st = o.get("status") or ("resolvido" if o.get("normalizado") else "aberto")
    if st == "resolvido":
        return "Concluído"
    if st in ("a_caminho", "em_atendimento"):
        return "Em atendimento"
    if st == "em_tratativa":
        mot = coletor_sem_acento(o.get("status_motivo") or "")
        if re.search(r"peca|material|compra|cabo|equipamento|orcamento|nobreak|inversor novo", mot):
            return "Pendente - Material"
        if re.search(r"concession|terceiro|fornecedor|provedor|enel|neoenergia|cemig|light|copel|coelba|energisa|equatorial|cliente|transportadora", mot):
            return "Pendente - Terceiros"
        return "Pendente - Equipe"
    return "Pendente - Equipe"


def coletor_sem_acento(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _chave_usina_diario(o):
    import coletor
    cod = coletor.chave_codigo(o.get("codigo")) if o.get("codigo") else None
    if cod:
        return cod
    ass = coletor.assinatura(re.sub(r"\s*-\s*[A-Z]{2}\b.*$", "", coletor.rotulo_usina(o.get("usina") or "")))
    # grupo sem código ("UFV Pradopolis - SP"): o código aprendido do COG com o mesmo nome (PRA100)
    for c, nome in codigos().items():
        if coletor.mesma_usina(ass, coletor.assinatura(nome)):
            return coletor.chave_codigo(c) or c
    return " ".join(sorted(ass[0])) + "|" + " ".join(sorted(ass[1]))


def episodios_diario(ocs, inicio_ts):
    """Uma linha por atendimento: junta os avisos da mesma usina que se sobrepõem no tempo e deixa de fora
    o que não é registro de diário (queda curta sem técnico nem OS, e o antigo que só 'fechou' por falta de aviso)."""
    agora = time.time()
    fim_de = lambda o: (o.get("normalizado") or {}).get("ts") or agora
    grupos = {}
    for o in sorted(ocs, key=lambda o: o["inicio_ts"]):
        grupos.setdefault(_chave_usina_diario(o), []).append(o)
    eps = []
    for lista in grupos.values():
        atual = None
        for o in lista:
            if atual and o["inicio_ts"] <= atual["_fim"] + 1800:
                atual["_membros"].append(o)
                atual["_fim"] = max(atual["_fim"], fim_de(o))
            else:
                atual = {"_membros": [o], "_fim": fim_de(o)}
                eps.append(atual)
    saida = []
    for ep in eps:
        ms = ep["_membros"]
        abertas = [m for m in ms if not m.get("normalizado")]
        modelo = next((m for m in ms if re.search(r"Descri[çc][ãa]o:|Ocorr[êe]ncia:", (m.get("msg") or {}).get("texto") or "")), None) \
            or next((m for m in ms if m["sev"] == "critico"), ms[0])
        com_codigo = next((m for m in ms if m.get("codigo") and str(m["usina"]).startswith(m["codigo"])), None)
        base = abertas[-1] if abertas else max(ms, key=lambda m: m["normalizado"]["ts"])
        o = dict(base, usina=(com_codigo or base)["usina"], msg=modelo["msg"], inicio_ts=ms[0]["inicio_ts"],
                 sev="critico" if any(m["sev"] == "critico" for m in ms) else "alerta",
                 normalizado=None if abertas else base["normalizado"],
                 os=sorted({x for m in ms for x in (m.get("os") or [])}),
                 visitas=list(dict.fromkeys(x for m in ms for x in (m.get("visitas") or []))))
        norm = o["normalizado"]
        dura = (norm["ts"] if norm else agora) - o["inicio_ts"]
        sem_confirmacao = norm and norm.get("motivo") in ("inatividade", "sem_registro")
        if o["inicio_ts"] < inicio_ts and sem_confirmacao:
            continue  # antigo que só saiu por falta de aviso: não foi atendimento deste plantão
        if not (o["sev"] == "critico" or not norm or o["visitas"] or o["os"] or dura >= 3600):
            continue  # oscilação curta resolvida sozinha
        saida.append(o)
    return sorted(saida, key=lambda o: o["inicio_ts"])


def linha_diario(o, n):
    norm = o.get("normalizado")
    feitas = []
    if o.get("visitas"):
        feitas.append("Técnico na usina: " + ", ".join(o["visitas"]))
    if norm and norm.get("motivo") == "manual":
        nota = (norm.get("texto") or "").replace("encerrada no painel", "").strip(" :")
        feitas.append(f"Encerrada no painel {_hora(norm['ts'])}" + (f": {_limpo(nota, 120)}" if nota else ""))
    elif norm and norm.get("motivo") in ("inatividade", "sem_registro"):
        feitas.append(f"Sem confirmação de normalização nos grupos (sem novidade desde {_hora(o.get('ultima_ts') or norm['ts'])})")
    elif norm:
        feitas.append(f"Normalizada {_hora(norm['ts'])} ({norm.get('de') or ''}): {_limpo(norm.get('texto'), 140)}")
    elif o.get("status_motivo") and o.get("status") in ("a_caminho", "em_atendimento") and o.get("status_origem") != "manual":
        feitas.append(_limpo(o["status_motivo"], 140))
    if norm:
        a_fazer = "N/A"
    elif o.get("status") == "em_tratativa" and o.get("status_origem") == "manual":
        a_fazer = "A definir (ficou para outro momento)"
    elif o.get("status") == "em_tratativa" and o.get("status_motivo"):
        a_fazer = _limpo(re.sub(r"^\s*\*[^*]{0,80}\*", "", o["status_motivo"].split(": ", 1)[-1]), 160)
    else:
        a_fazer = "Acompanhar até a normalização"
    return [str(n), _limpo(o.get("usina"), 60), _o_que_houve(o), " · ".join(feitas) or "—", "Não", "Grupo WhatsApp",
            a_fazer, "", _status_diario(o), ", ".join(o.get("os") or [])]


def _clima(o):
    try:
        import clima
        return clima.de(o)
    except Exception:
        return None


def linha_do_tempo(ocs, inicio, fim):
    """Barras do aviso até a normalização de cada ocorrência, na escala do período do plantão."""
    if not ocs or fim <= inicio:
        return ""
    total = fim - inicio
    pos = lambda ts: max(0.0, min(100.0, (ts - inicio) / total * 100))
    cores = {"critico": "#d62839", "alerta": "#e0a100", "ok": "#2e9e5b", "cinza": "#9aa3b2"}
    linhas = []
    for o in sorted(ocs, key=lambda o: o["inicio_ts"]):
        nz = o.get("normalizado")
        f = nz["ts"] if nz and nz["ts"] <= fim else fim
        cor = cores["cinza"] if nz and nz.get("motivo") in ("inatividade", "sem_registro") else cores["ok"] if nz and nz["ts"] <= fim else cores[o["sev"]]
        titulo = f"{o['usina']}: {_hora(o['inicio_ts'])} → {_hora(f) if nz and nz['ts'] <= fim else 'em aberto'} ({_dur(f - o['inicio_ts'])})"
        linhas.append(f"<div class='l' title='{html.escape(titulo)}'><div class='n'>{html.escape(o['usina'])}</div><div class='t'>"
                      f"<div class='b' style='left:{pos(o['inicio_ts']):.2f}%;width:{max(0.4, pos(f) - pos(o['inicio_ts'])):.2f}%;background:{cor}'></div></div></div>")
    marcas = [inicio + total * i / 4 for i in range(5)]
    return ("<h2>Linha do tempo do plantão</h2><div class='tl'><div class='leg'><i style='background:#d62839'></i>crítica em aberto"
            "<i style='background:#e0a100'></i>alerta em aberto<i style='background:#2e9e5b'></i>normalizada"
            "<i style='background:#9aa3b2'></i>sem confirmação</div>" + "".join(linhas) +
            "<div class='eixo'>" + "".join(f"<span>{_hora(t)}</span>" for t in marcas) + "</div></div>")


def salvar(inicio_ts, fim_ts, painel, plantao=None):
    pagina, texto = montar(inicio_ts, fim_ts, painel, plantao)
    pasta = config.pasta_relatorios()
    os.makedirs(pasta, exist_ok=True)
    base = os.path.join(pasta, "passagem-" + dt.datetime.fromtimestamp(fim_ts).strftime("%Y-%m-%d-%Hh%M"))
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(pagina)
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    return base + ".html"
