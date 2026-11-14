#!/usr/bin/env bash
# Instala o Centro de Operações no Linux (rodar de dentro da pasta clonada do GitHub).
#   bash instalar.sh --nome "Fulano" [--apelidos "Fulano Silva,Fulaninho"] [--organizacao "O&M · EMPRESA"] [--kmz ~/usinas.kmz]
# Sem os parâmetros, pergunta. Pode rodar de novo a qualquer momento (não apaga nada; atualiza o que precisar).
set -euo pipefail

PASTA="$(cd "$(dirname "$0")" && pwd)"
NOME="" APELIDOS="" ORG="" KMZ="" PORTA=47900
while [ $# -gt 0 ]; do
  case "$1" in
    --nome) NOME="$2"; shift 2 ;;
    --apelidos) APELIDOS="$2"; shift 2 ;;
    --organizacao) ORG="$2"; shift 2 ;;
    --kmz) KMZ="$2"; shift 2 ;;
    --porta) PORTA="$2"; shift 2 ;;
    *) echo "parâmetro desconhecido: $1"; exit 1 ;;
  esac
done

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
aviso(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
erro() { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }

echo "== Centro de Operações · instalação (Linux) =="

# 1) requisitos
command -v python3 >/dev/null || erro "Python 3 não encontrado (instale python3)."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || erro "Precisa de Python 3.9 ou mais novo."
ok "Python $(python3 -c 'import platform; print(platform.python_version())')"
command -v git >/dev/null || erro "git não encontrado (instale git)."
ok "git"
WA="$(python3 -c "import sys; sys.path.insert(0, '$PASTA'); import config; print(config.wa_comando())")"
[ -x "$WA" ] || erro "Comando 'wa' do wa-app não encontrado. Instale o wa-app e faça o login no WhatsApp primeiro."
"$WA" estado --json >/dev/null 2>&1 || erro "O wa-app não respondeu ('wa estado'). Abra o wa-app e confira se o WhatsApp está conectado."
ok "wa-app respondendo ($WA)"
if command -v tailscale >/dev/null && tailscale ip -4 >/dev/null 2>&1; then
  ok "Tailscale conectado ($(tailscale ip -4 | head -1))"
else
  aviso "Tailscale não está instalado ou conectado: o painel funciona no PC, mas o celular só conecta com Tailscale (tailscale.com/download)."
fi

# 2) perfil do usuário
[ -n "$NOME" ] || read -rp "  Seu nome, como te chamam nos grupos (ex.: Mateus): " NOME
[ -n "$ORG" ] || read -rp "  Organização/equipe para o topo do painel (opcional, ex.: O&M · EMPRESA): " ORG || true
DADOS="$(CO_PASTA="$PASTA" CO_NOME="$NOME" CO_APELIDOS="$APELIDOS" CO_ORG="$ORG" CO_KMZ="$KMZ" CO_PORTA="$PORTA" \
  python3 "$PASTA/ferramentas/configurar.py")"
ok "configuração em $DADOS/config.json"

# 3) serviço que liga junto com o PC
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/centro-operacoes.service" <<EOF
[Unit]
Description=Centro de Operações (painel de plantão sobre o wa-app) em http://127.0.0.1:$PORTA
After=graphical-session.target

[Service]
ExecStart=$(command -v python3) $PASTA/servidor.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical-session.target default.target
EOF
cat > "$HOME/.config/systemd/user/centro-operacoes-backup.service" <<EOF
[Unit]
Description=Backup diário do Centro de Operações

[Service]
Type=oneshot
ExecStart=$(command -v python3) $PASTA/backup.py
EOF
cat > "$HOME/.config/systemd/user/centro-operacoes-backup.timer" <<EOF
[Unit]
Description=Backup diário do Centro de Operações (03:30)

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now centro-operacoes.service >/dev/null
systemctl --user enable --now centro-operacoes-backup.timer >/dev/null
ok "serviço centro-operacoes ligado (liga sozinho com o PC) e backup diário às 03:30"

# 4) atalho de app (PWA): janela própria no Chrome/Edge/Chromium/Brave; sem nenhum deles, abre no navegador padrão
NAVEGADOR=""
for b in google-chrome-stable google-chrome chromium chromium-browser microsoft-edge-stable microsoft-edge brave-browser; do
  if command -v "$b" >/dev/null; then NAVEGADOR="$b"; break; fi
done
URL="http://127.0.0.1:$PORTA"
if [ -n "$NAVEGADOR" ]; then EXEC="$NAVEGADOR --app=$URL --class=CentroOperacoes"; else EXEC="xdg-open $URL"; fi
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/centro-operacoes.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Centro de Operações
Comment=Plantão das usinas sobre o WhatsApp (wa-app)
Exec=$EXEC
Icon=$PASTA/pwa/icone-512.png
Categories=Office;Network;
StartupWMClass=CentroOperacoes
EOF
DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESKTOP" ]; then
  cp "$HOME/.local/share/applications/centro-operacoes.desktop" "$DESKTOP/" && chmod +x "$DESKTOP/centro-operacoes.desktop"
fi
ok "atalho 'Centro de Operações' no menu e na área de trabalho${NAVEGADOR:+ (app em janela própria pelo $NAVEGADOR)}"

# 5) espera a primeira sincronização
printf '  … aguardando o painel ler o WhatsApp pela primeira vez'
for i in $(seq 1 60); do
  if curl -s "$URL/api/dados" 2>/dev/null | grep -q '"pronto": true'; then echo; ok "painel no ar em $URL"; break; fi
  printf '.'; sleep 3
done

cat <<EOF

== Pronto! ==
  • Abra "Centro de Operações" no menu (ou $URL).
  • Celular (Android): no painel, toque em "📱 Conectar celular" e siga o QR.
  • Mapa: coloque o KMZ das suas usinas em $DADOS/usinas.kmz (ou rode de novo com --kmz).
  • Atualizações: o painel avisa quando sair versão nova (botão ATUALIZAR AGORA).
EOF
