# Indicadores do Centro de Operações: ocorrências (histórico de 30+ dias) e o Diário de Chamados.
import datetime as dt, re, statistics, time
import coletor, relatorio

TIPOS = [  # ordem de prioridade: a primeira que casar define o tipo da ocorrência
    ("Desarme / disjuntor", re.compile(r"desarm|disjuntor|\btrip|tripou|protecao|rele|religa|52l|sobretensao|subtensao|parada")),
    ("Comunicação", re.compile(r"comunica|logger|offline|fora do ar|scada|monitoramento")),
    ("Inversor", re.compile(r"inversor")),
    ("Tracker", re.compile(r"tracker|rastreador")),
    ("Energia / concessionária", re.compile(r"concessionaria|falta de energia|apagao|alimentador|rede")),
]
CONFIRMADAS = ("cog", "mensagem", "manual")  # normalização que alguém confirmou (não por inatividade)


def de_usina(o):
    """Só ocorrências de uma usina identificada (conversa solta de grupo geral não entra nos números)."""
    return not o.get("generico") and (o.get("codigo") or re.search(r"\bUFV|usina", o.get("usina") or "", re.I))


def tipo_de(o):
    t = coletor.sem_acento(o["msg"]["texto"])
    return next((nome for nome, rx in TIPOS if rx.search(t)), "Outros")


def clientes_por_codigo(mapa):
    """KMZ: 'Solar - Atualizado 01/10/2026 / Gera / Blackout' → cliente 'Gera' para o código da usina."""
    out = {}
    for p in (mapa or {}).get("pontos", []):
        if p.get("categoria") != "usina":
            continue
        partes = [x for x in (p.get("pasta") or "").split(" / ") if x]
        cliente = partes[1] if len(partes) > 1 and partes[0].lower().startswith(("solar", "biog")) else (partes[-1] if partes else "")
        out[coletor_chave(p["nome"])] = cliente or "Outros"
    return out


def coletor_chave(codigo):
    m = re.match(r"^([A-Z]{2,4})(\d)", codigo or "")
    return m.group(1) + m.group(2) if m else (codigo or "")


def calcular(dias, cliente, painel, mapa):
    agora = time.time()
    inicio = agora - dias * 86400
    hist = relatorio._ler(relatorio.HIST, {})
    for o in painel.get("ocorrencias", []):  # o ao vivo (com ciente/encerrar aplicados) vale mais que o guardado
        hist[o["chave"]] = o
    por_cod = clientes_por_codigo(mapa)

    def cliente_de(o):
        cod = (o.get("codigo") or "").split("/")[0]
        return por_cod.get(coletor_chave(cod), "Sem cliente identificado") if cod else "Sem cliente identificado"

    ocs = [o for o in hist.values() if o["inicio_ts"] >= inicio and de_usina(o)]
    clientes = sorted({cliente_de(o) for o in ocs})
    if cliente:
        ocs = [o for o in ocs if cliente_de(o) == cliente]

    # série no tempo: por hora (até 2 dias) ou por dia
    passo = 3600 if dias <= 2 else 86400
    if passo == 86400:
        base = dt.datetime.fromtimestamp(inicio).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    else:
        base = inicio // 3600 * 3600
    n = int((agora - base) // passo) + 1
    serie = [{"t": int(base + i * passo), "critico": 0, "alerta": 0} for i in range(n)]
    for o in ocs:
        i = int((o["inicio_ts"] - base) // passo)
        if 0 <= i < n:
            serie[i][o["sev"]] += 1

    # reincidência e tempo até normalizar, por usina
    por_usina = {}
    for o in ocs:
        u = por_usina.setdefault(o["usina"], {"usina": o["usina"], "total": 0, "criticas": 0, "tempos": []})
        u["total"] += 1
        u["criticas"] += o["sev"] == "critico"
        nz = o.get("normalizado")
        if nz and nz.get("motivo", "mensagem") in CONFIRMADAS:
            u["tempos"].append(max(0, nz["ts"] - o["inicio_ts"]))
    reincidencia = sorted(por_usina.values(), key=lambda u: (-u["total"], -u["criticas"]))[:10]
    tempo_usina = sorted([{"usina": u["usina"], "mediana_h": round(statistics.median(u["tempos"]) / 3600, 1), "n": len(u["tempos"])}
                          for u in por_usina.values() if u["tempos"]], key=lambda u: -u["mediana_h"])[:10]
    for u in reincidencia:
        u.pop("tempos", None)

    tempos = [o["normalizado"]["ts"] - o["inicio_ts"] for o in ocs
              if o.get("normalizado") and o["normalizado"].get("motivo", "mensagem") in CONFIRMADAS]
    tipos = {}
    for o in ocs:
        tipos[tipo_de(o)] = tipos.get(tipo_de(o), 0) + 1
    por_cliente = {}
    for o in [o for o in hist.values() if o["inicio_ts"] >= inicio and de_usina(o)]:
        c = cliente_de(o)
        por_cliente[c] = por_cliente.get(c, 0) + 1

    # Diário: chamados por mês (todos os meses com dados), chamados por usina no período, tarefas por técnico
    chamados = (painel.get("chamados") or []) + (painel.get("chamados_fechados_todos") or [])
    meses = {}
    for c in chamados:
        mes = (c.get("data") or "")[:7]
        if len(mes) == 7:
            st = c.get("status") or "Pendente"
            meses.setdefault(mes, {"mes": mes, "Resolvido": 0, "Em andamento": 0, "Pendente": 0})
            meses[mes][st if st in ("Resolvido", "Em andamento", "Pendente") else "Pendente"] += 1
    corte = dt.datetime.fromtimestamp(inicio).strftime("%Y-%m-%d")
    ch_usina = {}
    for c in chamados:
        if (c.get("data") or "") >= corte:
            u = ch_usina.setdefault(c.get("usina") or "—", {"usina": c.get("usina") or "—", "total": 0, "abertos": 0})
            u["total"] += 1
            u["abertos"] += coletor.aberto(c.get("status"), "chamado")
    tarefas = (painel.get("tarefas") or []) + (painel.get("tarefas_fechadas_todas") or [])
    por_tec = {}
    for t in tarefas:
        if (t.get("data") or "") >= corte:
            x = por_tec.setdefault(t.get("tecnico") or "—", {"tecnico": t.get("tecnico") or "—", "abertas": 0, "concluidas": 0})
            x["abertas" if coletor.aberto(t.get("status"), "tarefa") else "concluidas"] += 1

    return {
        "dias": dias, "cliente": cliente, "clientes": clientes, "inicio": int(inicio), "passo": passo,
        "importado_desde": int(min([o["inicio_ts"] for o in hist.values()] or [agora])),
        "resumo": {
            "total": len(ocs), "criticas": sum(o["sev"] == "critico" for o in ocs),
            "abertas": sum(not o.get("normalizado") for o in ocs),
            "confirmadas": len(tempos),
            "mediana_h": round(statistics.median(tempos) / 3600, 1) if tempos else None,
            "usinas": len(por_usina),
        },
        "serie": serie, "reincidencia": reincidencia, "tempo_usina": tempo_usina,
        "tipos": sorted(({"tipo": k, "n": v} for k, v in tipos.items()), key=lambda x: -x["n"]),
        "por_cliente": sorted(({"cliente": k, "n": v} for k, v in por_cliente.items()), key=lambda x: -x["n"]),
        "chamados_mes": [meses[k] for k in sorted(meses)][-6:],
        "chamados_usina": sorted(ch_usina.values(), key=lambda u: -u["total"])[:10],
        "tarefas_tecnico": sorted(por_tec.values(), key=lambda x: -(x["abertas"] + x["concluidas"]))[:10],
    }
