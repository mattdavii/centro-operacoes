#!/usr/bin/env bash
# Publica uma versão nova do Centro de Operações (uso do mantenedor):
#   ./publicar.sh "o que mudou nesta versão"
# Sobe o número em VERSAO, roda os testes, gera o APK e o PDF, faz commit + tag vN, envia ao GitHub e cria a
# Release com o APK. A partir daí, os PCs instalados mostram "Nova versão" e os celulares recebem a notificação.
set -euo pipefail
cd "$(dirname "$0")"
NOTAS="${1:?uso: ./publicar.sh \"o que mudou\"}"

python3 testes/test_normalizacao.py
VERSAO=$(( $(cat VERSAO) + 1 ))
echo "$VERSAO" > VERSAO
android/build.sh
if [ -x .venv-docs/bin/python ]; then .venv-docs/bin/python docs/gerar_pdf.py; fi

git add -A
git commit -q -m "v$VERSAO: $NOTAS

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git tag -a "v$VERSAO" -m "v$VERSAO: $NOTAS"
git push -q origin HEAD --follow-tags

ANEXOS=(dist/CentroOperacoes.apk)
[ -f docs/Centro-de-Operacoes.pdf ] && ANEXOS+=(docs/Centro-de-Operacoes.pdf)
gh release create "v$VERSAO" "${ANEXOS[@]}" --title "Centro de Operações v$VERSAO" --notes "$NOTAS" --latest
echo "publicado: v$VERSAO"
