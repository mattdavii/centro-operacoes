# Centro de Operações

Painel de plantão para equipes de O&M de usinas solares que usam o **wa-app** (WhatsApp local, **só leitura**).
Ele lê os grupos e conversas e mostra, ao vivo:

- **Ocorrências** detectadas nas mensagens (desarme, trip, falha, sem comunicação…), agrupadas por usina, com baixa automática só quando a normalização é confirmada (COG 🟩, "usina religada", "pode encerrar a OS"); sem novidade por 6 h, o painel pergunta se continua (nada fecha sozinho por tempo).
- **Manutenções e técnicos em campo**: atividades do COG (início, concluída, cancelada) e entrada/saída dos técnicos nas usinas; ocorrência que começa durante uma manutenção é marcada e não toca alarme. Aba **Manutenções** para acompanhar e encerrar na mão quando o grupo não avisar.
- **Conversas aguardando você** (privado, ou grupo onde te marcaram/citaram).
- **Mapa** das usinas (a partir do seu KMZ), com os técnicos mais próximos de cada ocorrência.
- **Tempo nas usinas**: chuva, trovoada e rajada na hora de cada ocorrência (Open-Meteo, grátis e sem chave) e os avisos meteorológicos do INMET sobre as usinas, no painel, no mapa, nos indicadores e no relatório. Só as coordenadas das usinas (arredondadas a ~10 km) saem do PC.
- **Indicadores**: ocorrências por dia, usinas reincidentes, tempo até normalizar, tipos de falha, por cliente.
- **Plantão**: iniciar/finalizar, linha do tempo e relatório de passagem (PDF e texto para WhatsApp).
- **App Android** com alarme (horário de silêncio configurável), cache offline e conexão por QR.

## Instalação

Veja **[INSTALAR.md](INSTALAR.md)** (Linux e Windows; dá para pedir ao Claude Code que instale) e o guia em PDF em [`docs/`](docs/).

- App Android (última versão): https://github.com/mattdavii/centro-operacoes/releases/latest/download/CentroOperacoes.apk

## Como funciona

- `servidor.py`: servidor local (porta 47900) que sincroniza com o wa-app a cada minuto e serve o painel (PWA). Acesso remoto só pelo Tailscale e com senha (token criado na instalação).
- `coletor.py`: regras de ocorrências e normalizações (testes em `testes/test_normalizacao.py`, com casos reais anonimizados).
- `android/`: app Android sem Gradle (`android/build.sh`), pareado com o PC por QR.
- `publicar.sh`: gera a versão, o APK e a Release no GitHub (uso do mantenedor).

Nada de mensagens, senhas ou dados de usinas fica no repositório: tudo isso mora só no PC de cada usuário.
