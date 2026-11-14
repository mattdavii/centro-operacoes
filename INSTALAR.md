# Instalar o Centro de Operações

Painel de plantão para quem usa o **wa-app** (o WhatsApp local, só leitura): ocorrências das usinas detectadas nos grupos, mapa, indicadores, relatório de passagem de plantão e alarme no celular Android.

## Jeito mais fácil: pedir para o Claude

No **Claude Code** (no PC onde o wa-app está instalado), cole:

```
Instale o Centro de Operações deste repositório no meu PC: https://github.com/mattdavii/centro-operacoes
Siga o INSTALAR.md (seção "Para o Claude"). Meu nome nos grupos é <SEU NOME> e minha equipe é <SUA EQUIPE>.
```

O Claude confere os requisitos, instala, liga o serviço e cria o atalho do app.

## O que precisa ter antes

| Item | Para quê |
|---|---|
| **wa-app** instalado e conectado ao WhatsApp | é de onde vêm as mensagens (o painel só lê, nunca envia) |
| **Python 3.9+** e **git** | rodar e atualizar o painel |
| **Google Chrome** ou **Microsoft Edge** | abrir o painel como app (PWA) |
| **Tailscale** no PC e no celular, mesma conta | o celular falar com o PC de qualquer lugar, com segurança |
| Celular **Android** | o app de alarmes (iPhone não é suportado) |

## Para o Claude

Siga na ordem e pare para avisar o usuário se algum requisito faltar.

1. Confira os requisitos: `wa estado --json` responde (no Windows o comando pode ser `wa.cmd`), Python ≥ 3.9, git, e se `tailscale ip -4` devolve um IP (se não, avise que o celular só conecta com Tailscale, mas continue).
2. Clone o repositório:
   - Linux: `git clone https://github.com/mattdavii/centro-operacoes ~/centro-operacoes`
   - Windows: `git clone https://github.com/mattdavii/centro-operacoes $env:USERPROFILE\centro-operacoes`
3. Pergunte ao usuário o **nome** como ele é chamado nos grupos, **apelidos** (opcional), a **equipe/organização** (opcional) e se ele tem um **KMZ das usinas** (opcional, para o mapa).
4. Rode o instalador:
   - Linux: `bash ~/centro-operacoes/instalar.sh --nome "NOME" --apelidos "A,B" --organizacao "EQUIPE" [--kmz CAMINHO.kmz]`
   - Windows (PowerShell): `powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\centro-operacoes\instalar.ps1 -Nome "NOME" -Apelidos "A,B" -Organizacao "EQUIPE" [-Kmz CAMINHO.kmz]`
   - No Windows, a liberação do firewall para o celular precisa de PowerShell **como administrador**; se o instalador avisar, mostre o comando ao usuário.
5. Confirme que o painel está no ar: `http://127.0.0.1:47900/api/dados` deve ter `"pronto": true` (a primeira leitura do WhatsApp leva ~30 s).
6. Explique ao usuário os próximos passos: abrir o atalho **Centro de Operações**, tocar em **📱 Conectar celular** e seguir o QR; e que o painel avisa quando sair versão nova.

Nada do usuário vai para o GitHub: configuração, senha do celular e histórico ficam só no PC dele
(Linux `~/.local/share/centro-operacoes`, Windows `%LOCALAPPDATA%\CentroOperacoes`).

## Celular (Android)

1. Instale o **Tailscale** no celular e entre com a mesma conta do PC.
2. Baixe o app: **https://github.com/mattdavii/centro-operacoes/releases/latest/download/CentroOperacoes.apk** (permita "instalar apps desta fonte").
3. No PC, em **📱 Conectar celular**, aponte a câmera para o QR e toque em **CONECTAR ESTE CELULAR**.
4. Permita as notificações e "não otimizar bateria", e use **🔔 Testar alarme** no PC para conferir.

## Atualizações

- **PC:** quando sair versão nova, aparece a faixa **"Nova versão do Centro de Operações"** com o botão **ATUALIZAR AGORA** (faz `git pull` e reinicia sozinho).
- **Celular:** a tela se atualiza sozinha; quando o app nativo muda, chega a notificação **"Nova versão do Centro de Operações"**: é só tocar e instalar.

## Configuração (opcional)

Arquivo `config.json` na pasta de dados:

| Campo | O que faz |
|---|---|
| `nome_usuario`, `apelidos` | "citou seu nome" nos grupos |
| `organizacao` | texto no topo do painel |
| `kmz` | KMZ das usinas (padrão: `usinas.kmz` na pasta de dados) |
| `silencio_inicio`, `silencio_fim` | horário sem som (padrão 20h às 7h) |
| `pasta_relatorios`, `pasta_backup` | onde salvar relatórios de plantão e backups |
| `diario_py`, `diario_python` | integração com a planilha Diário de Chamados (só para quem tem) |
| `wa` | caminho do comando `wa`, se não for achado sozinho |
| `porta` | porta do painel (padrão 47900) |

Outro arquivo útil: `vinculos.json` (quando o painel separar a mesma usina em duas: `"CÓDIGO": "nome do grupo"`).
