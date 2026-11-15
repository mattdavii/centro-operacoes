#!/usr/bin/env python3
# Reconstrói as ocorrências dos últimos N dias a partir do WhatsApp (wa-app, só leitura), com as mesmas regras
# do painel, e junta ao histórico (~/.local/share/atendimentos/ocorrencias.json). Não mexe nas últimas 24 h,
# que são do painel ao vivo.
#   historico.py [--dias 7] [--substituir]   (--substituir refaz o que é anterior às últimas 24 h)
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coletor, relatorio

DIAS = int(sys.argv[sys.argv.index("--dias") + 1]) if "--dias" in sys.argv else 7  # padrão: 1 semana


def ler_periodo(jid, ini, fim, prof=0):
    """Lê as mensagens de [ini, fim); se bater no limite de 1000 do wa, divide o período ao meio."""
    import datetime as dt
    iso = lambda t: dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="minutes")
    d = coletor.wa("read", jid, "--since", iso(ini), "--until", iso(fim), "--limit", "1000", timeout=120)
    ms = d.get("messages") or []
    if len(ms) >= 1000 and prof < 8 and fim - ini > 1800:
        meio = (ini + fim) / 2
        return ler_periodo(jid, ini, meio, prof + 1) + ler_periodo(jid, meio, fim, prof + 1), d.get("chat")
    return ms, d.get("chat")


def main():
    agora = time.time()
    inicio = agora - DIAS * 86400
    chats = [c for c in coletor.chats_ativos(DIAS) if c.get("isGroup")]
    print(f"{len(chats)} grupos com mensagens nos últimos {DIAS} dias", flush=True)
    eventos, usinas, total = [], [], 0
    for i, c in enumerate(chats, 1):
        msgs, info, vistos = [], None, set()
        passo = 3 * 86400
        t = inicio
        while t < agora:
            parte, info = ler_periodo(c["jid"], t, min(agora, t + passo))
            for m in parte:
                if m.get("id") not in vistos:
                    vistos.add(m.get("id")); msgs.append(m)
            t += passo
        total += len(msgs)
        op = coletor.operacao(c, {"messages": msgs, "chat": info or {"name": c.get("name"), "isGroup": True}},
                              agora=agora, janela=DIAS * 86400)
        eventos += op["eventos"]
        if op["usina"]:
            usinas.append(dict(op["usina"]))
        print(f"[{i}/{len(chats)}] {c.get('name', '')[:40]}: {len(msgs)} mensagens, {len(op['eventos'])} eventos", flush=True)
    ocorrencias, usinas, _ = coletor.montar_ocorrencias(eventos, usinas, coletor.ler_vinculos())
    cod_grupo = {u["jid"]: u.get("codigo") for u in usinas if u.get("codigo")}
    limite_ao_vivo = agora - 24 * 3600
    for o in ocorrencias:
        o["codigo"] = cod_grupo.get(o["chave_usina"]) or next(
            (e["codigo"] for e in eventos if e.get("codigo") and e["chave_usina"] == o["chave_usina"]), None)
        # crítica antiga sem normalização no WhatsApp: não fica "aberta" para sempre no histórico
        if not o["normalizado"] and o["ultima_ts"] < limite_ao_vivo:
            o["normalizado"] = {"ts": o["ultima_ts"], "de": "histórico", "motivo": "sem_registro",
                                "texto": "sem normalização registrada no WhatsApp"}
    hist = relatorio._ler(relatorio.HIST, {})
    if "--substituir" in sys.argv:
        # refaz o passado com as regras atuais: tira o que não é do painel ao vivo e grava de novo
        hist = {k: v for k, v in hist.items()
                if (v.get("ultima_ts", 0) >= limite_ao_vivo and not v.get("importada")) or v.get("inicio_ts", 0) < inicio}
    novas = 0
    for o in ocorrencias:
        if o["ultima_ts"] < limite_ao_vivo and not o.get("generico") and o["chave"] not in hist:
            o["importada"] = True
            hist[o["chave"]] = o
            novas += 1
    relatorio._gravar(relatorio.HIST, hist)
    # manutenções do COG e visitas (entrada/saída) do mesmo período
    atividades, presencas = coletor.montar_manutencoes(eventos, usinas, ocorrencias, agora=agora)
    for arq, itens, campo in ((relatorio.MANUT, atividades, "inicio_ts"), (relatorio.VISITAS, presencas, "entrada_ts")):
        h = relatorio._ler(arq, {})
        if "--substituir" in sys.argv:
            h = {k: v for k, v in h.items() if v.get(campo, 0) >= limite_ao_vivo or v.get(campo, 0) < inicio}
        for i in itens:
            if i[campo] < limite_ao_vivo and i["chave"] not in h:
                h[i["chave"]] = i
        relatorio._gravar(arq, h)
    print(f"manutenções: {len(atividades)} · visitas: {len(presencas)}", flush=True)
    print(f"pronto: {total} mensagens lidas, {len(ocorrencias)} ocorrências no período, {novas} novas no histórico "
          f"(total {len(hist)})", flush=True)


if __name__ == "__main__":
    main()
