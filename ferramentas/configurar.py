#!/usr/bin/env python3
# Grava o config.json do usuário a partir de variáveis de ambiente (usado pelos instaladores):
#   CO_PASTA (pasta do projeto), CO_NOME, CO_APELIDOS ("a,b"), CO_ORG, CO_KMZ (arquivo a copiar), CO_PORTA
# Mantém o que já existir; imprime a pasta de dados.
import json, os, shutil, sys
sys.path.insert(0, os.environ.get("CO_PASTA") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

e = os.environ.get
os.makedirs(config.DADOS, exist_ok=True)
atual = {}
if os.path.exists(config.ARQUIVO):
    with open(config.ARQUIVO, encoding="utf-8") as f:
        atual = json.load(f)
novo = dict(atual)
apelidos = [a.strip() for a in (e("CO_APELIDOS") or "").split(",") if a.strip()]
for k, v in {"nome_usuario": (e("CO_NOME") or "").strip(), "organizacao": (e("CO_ORG") or "").strip(),
             "apelidos": apelidos, "porta": int(e("CO_PORTA") or 0)}.items():
    if v:
        novo[k] = v
if e("CO_KMZ"):
    shutil.copyfile(os.path.expanduser(e("CO_KMZ")), os.path.join(config.DADOS, "usinas.kmz"))
for k, v in config.PADRAO.items():
    novo.setdefault(k, v)
with open(config.ARQUIVO, "w", encoding="utf-8") as f:
    json.dump(novo, f, ensure_ascii=False, indent=2)
print(config.DADOS)
