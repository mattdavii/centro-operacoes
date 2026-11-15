# Casos reais do WhatsApp (14/11/2026): o que pode e o que não pode dar baixa numa ocorrência.
#   python3 testes/test_normalizacao.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import coletor

erros = 0

DA_BAIXA = [
    "*UFV GOY700 – GOY700* *🔌🟩 Normalização: Disjuntor 52L Fechado* > Proteção atuada: em análise",
    "* *UFV RIO100 – L'oreal RJ* *🔌🟩 Normalização: Usina restabelecida* > Horário de restabelecimento: 15h05min",
    "UFV Monsenhor Tabosa religada.",
    "@COG Cliente UFV normalizada. Posso ajudar com mas alguma situação",
    "Retornou. Foi apenas uma oscilação.",
    "UFV CONCÓRDIA Religada!",
    "Usina religada as 07:01",
    "*✅ Atendimento Concluído* Informamos a conclusão do atendimento na UFV JAU100 – Jaú 100.",
    "Comunicação restabelecida, inversores 70, 71 e 73 já estão comunicando",
    "Foi realizado o fechamento do disjuntor e a usina está gerando normal",
    "Conexão restabelecida,@Centro Operação Gera conferir por favor. Por conta da falha do smartlogger,foi visto que localmente os inversores estão estao em geração .",
    "Tensão na rede normalizada",
    "Ta um pouco baixa, mas voltou kk",
    "PD encerra aqui a OS",
    "Pode encerrar a OS 5688, usina comunicando",
    "OS 5690 finalizada",
    "Normalizado",
    "*UFV ABC200 – Usina 2* > Com auxilio da vigilância novamente, constatamos que os inversores estão em operação",
    "a vigilância confirmou que estava ok",
    "@COG foi identificado o dinjuntor do padrão de entrada desarmado ( em trip) após as devidas verificações nada de anormal foi constatado disjuntor foi fechado",
    "* *UFV QSS100 – Quissamã 100* *🔌🟥 Ocorrência: Disjuntor 52L aberto* > Proteções atuadas: > • 27 (Subtensão) > Horário do desarme: 18h26min *🔌🟩 Normalização: Disjuntor 52L Fechado* > Horário de fechamento: 19h02min",
]
NAO_DA_BAIXA = [
    "o inversor precisa estar com o lado CA energizado (disjuntor CA fechado), senão o MBUS não fala.",
    "inversor 3 ainda não está em operação",
    "vamos verificar se está ok",
    "confirmou que estava ok antes do desarme, agora está parado",
    "No COV consta como disjuntor fechado, porém, via Fusion a usina não comunica há uns 15 minutos",
    "Boa tarde! @COG Cliente , movimentei o Tracker 02, via bateria externa para 0⁰, fiz o reset, vou esperar um pouco e restabelecer o mesmo!",
    "@Fulano COG me pontuou que o Inversor 6 do projeto não retornou para funcionamento",
    "De alto Paraná, 3 mobilizações, 1 para religamento e duas de check",
    "Pedi pra se o nobreak descarregar ele me informar se até lá não conseguir normalizar",
    "Posso solicitar o reestabelecimento para concessionária?",
    "Tensões normalizadas e tudo Ok na usina?",
    "Ele n voltou mais a ficar online?",
    "*UFV PTY100 – Paty dos Alferes 100 (Avelar)* *📞🗣️ Contato com o COD: Informação da linha* ⚡Concessionária: Light 👤Operador: Pedro > Em contato com o COD",
    "@Centro Operação Gera tem como verificar se o voltou o relé pf",
    "Blz, pode seguir com a Energização e informar o horário de religamento.",
    "Usina ainda não foi religada",
    "Assim que for restabelecida me avisa",
    "A usina voltou a desarmar",
    "*UFV PTY100 – Paty dos Alferes 100 (Avelar)* *📞🗣️ Contato com o COD: Informação da linha* ⚡Concessionária: Light 👤Operador: Pedro > Em contato com o COD, fomos informados que o alimentador *LSA Cambará* saltou por um momento, no entanto, foi religado minutos depois. O disjuntor de acoplamento da usina possivelmente abriu durante o transitório de energia. > Horário do contato: 08h58min",
    "Penedo comunicação parece que retornou, estamos verificando",
    "Inversor 05 religado, mas o inversor 06 continua em falha",
    "Posso encerrar a OS?",
]

# não são ocorrência: manobra/desligamento combinado
NAO_E_OCORRENCIA = [
    "A usina será desligada amanhã às 8h para a preventiva",
]

# gravidade: crítica só quando a usina toda está fora; falha só de inversor, de relé ou alarme falso é alerta
for frase, nivel in [
    ("sim sim leitura fica oscilando, alarmes de desarme fakes", "alerta"),
    ("Inversores desarmando por alarme de sobretensão. Abriremos um chamado com a rede da concessionária.", "alerta"),
    ("o inversor 06 segue parado", "alerta"),
    ("*ACIONAMENTO – CORRETIVA EMERGENCIAL* Usina: UFV ABC100 – X Descrição: Inversor 06 parado com alarme de baixa R.I", "alerta"),
    ("*ACIONAMENTO – CORRETIVA EMERGENCIAL* Usina: UFV ABC100 – X Descrição: Usina desarmada, disjuntor 52L aberto", "critico"),
    ("Usina desarmou por sobretensão", "critico"),
    # modelos padronizados do COG
    ("*UFV ABC100 – X* *🔌🟥 Ocorrência: Disjuntor 52L aberto* > Proteção atuada: 46 > Horário do desarme: 05h53min", "critico"),
    ("*UFV ABC100 – X* *📡🟥 Ocorrência: Falha de comunicação* > Usina sem comunicação > Técnico será direcionado", "alerta"),
    ("*UFV ABC100 – X* *⚙️🟥 Ocorrência: Inversor parado* > Inversor: 10 > Alarme: Fusível da Fase A aberto", "alerta"),
    ("*UFV ABC100 – X* *⚙️🟥 Ocorrência: Inversores parados com alarme de falha de energia* > Horário da parada: 17h42min", "critico"),
    ("*UFV ABC100 – X* *🌡️♨️ Ocorrência: Inversor limitado para controle de temperatura* > Inversor 01 a 120 kW", "alerta"),
    ("*UFV ABC100 – X* *🔌✅ Ocorrência: Disjuntor 52L aberto* > Horário do desarme: 15h00min > Horário do rearme : 15h05min", "normal"),
    ("*UFV ABC100 – X* *⚙️🟩 Normalização: Inversor em operação* > Inversor: 10", "normal"),
    ("*UFV ABC100 – X* *⚡📝 Chamado aberto* > Concessionária: Copel > Aberto chamado referente a: Falta de energia", "acompanha"),
    ("*UFV ABC100 – X* *📞🗣️ Contato com o COD: Informação da linha* > Estamos acompanhando", "acompanha"),
    ("*UFV ABC100 – X* *📡🛜🗣️🗣️ Mensagem do provedor* > técnicos a caminho", "acompanha"),
    ("*🚨 Atendimento Emergencial em Andamento* Identificamos uma ocorrência na UFV ABC100 – X. 🆔 OS: 1 🔎 Descrição: Usina em falha de comunicação total - Necessário validar 👷 Nossa equipe técnica já foi acionada", "critico"),
    ("*🚨 ACIONAMENTO – CORRETIVA EMERGENCIAL* 📍 Usina: UFV ABC100 – X 🔎 Descrição: Rearmar usina 👷 Técnico acionado: Fulano", "critico"),
    ("*🚨 ACIONAMENTO – CORRETIVA EMERGENCIAL* 📍 Usina: UFV ABC100 – X 🔎 Descrição: Eletrocentros 1,3 e 4 parados. 👷 Técnico acionado: Fulano", "critico"),
    ("*🚨 ACIONAMENTO – CORRETIVA EMERGENCIAL* 📍 Usina: UFV ABC100 – X 🔎 Descrição: Trackers fora de posição 👷 Técnico acionado: Fulano", "alerta"),
    ("*RESUMO - UFV X* * Inversores 2 e 3, com potência reduzida * Nobreak da Cabine com problema", None),
    ("*🚨 ACIONAMENTO – CORRETIVA EMERGENCIAL* Usina em falha de comunicação total, inversor sem dados", "critico"),
]:
    if coletor.classificar(coletor.sem_acento(frase)) != nivel:
        erros += 1
        print("✗ gravidade:             ", frase, "→", coletor.classificar(coletor.sem_acento(frase)), "(esperado", nivel + ")")
# "Usina Itaperuna" (sem "UFV") também identifica a usina
for frase, nome in [("Identificamos uma ocorrência na Usina Itaperuna. 🆔 OS: 5697", "Itaperuna"),
                    ("Usina desarmada por sobretensão", None)]:
    if coletor.extrair_nome_usina(frase) != nome:
        erros += 1
        print("✗ nome da usina:         ", frase, "→", coletor.extrair_nome_usina(frase))

# são ocorrência (usina ainda parada esperando atendimento), mesmo sem palavra de falha
E_OCORRENCIA = [
    "Só confirmando a posição das chaves. Por gentileza, manter informação que o projeto vai estar desligado na transferência de plantão.",
    "Para enviar um terceiro amanhã para religar o projeto.",
    "Usina continua desligada, técnico vai amanhã",
]

for t in DA_BAIXA:
    if coletor.classificar(coletor.sem_acento(t)) != "normal":
        erros += 1
        print("✗ deveria dar baixa:     ", t[:100])
for t in NAO_DA_BAIXA:
    if coletor.classificar(coletor.sem_acento(t)) == "normal":
        erros += 1
        print("✗ NÃO deveria dar baixa: ", t[:100])
for t in NAO_E_OCORRENCIA:
    if coletor.classificar(coletor.sem_acento(t)) in ("critico", "alerta"):
        erros += 1
        print("✗ NÃO é ocorrência:      ", t[:100])
for t in E_OCORRENCIA:
    if coletor.classificar(coletor.sem_acento(t)) not in ("critico", "alerta"):
        erros += 1
        print("✗ É ocorrência:          ", t[:100])

# a mesma pessoa se corrige logo em seguida: a baixa não vale
base = 1_000_000
msgs = [{"id": "a", "ts": base, "sender": "me", "text": "Ta um pouco baixa, mas voltou kk"},
        {"id": "b", "ts": base + 60, "sender": "me", "text": "Mas ainda ta abaixo dos 5%.. usina talvez não segure"}]
if not coletor.desmentida(msgs[0], msgs):
    erros += 1
    print("✗ correção logo depois deveria desfazer a baixa")
msgs2 = [{"id": "a", "ts": base, "sender": "x", "text": "Usina religada as 07:01"},
         {"id": "b", "ts": base + 60, "sender": "x", "text": "Bom dia a todos"}]
if coletor.desmentida(msgs2[0], msgs2):
    erros += 1
    print("✗ mensagem comum depois não deveria desfazer a baixa")
# volta de comunicação não fecha crítica de desarme (Mucugê 14/11: usina parada esperando o técnico)
for frase, so_com in [("Comunicação do Relé LT retornou", True), ("Comunicação restabelecida, usina gerando normal", False),
                      ("Usina religada as 07:01", False), ("Logger voltou a comunicar", True), ("PD encerra aqui a OS", False)]:
    if coletor.so_comunicacao(coletor.sem_acento(frase)) != so_com:
        erros += 1
        print("✗ só comunicação errado:  ", frase)
# manutenções (atividade do COG) e técnicos em campo (entrada/saída)
for frase, esperado in [
    ("* *UFV GOY100* *⚙️🧰 Atividade: Roçada* > Trackers do 12 ao 24 movidos", ("atividade_inicio", "Roçada", None, None)),
    ("*UFV GOY100 – GOY100* *⚙️🟩 Atividade concluída: Roçada* > Trackers liberados", ("atividade_fim", "Roçada", None, None)),
    ("*UFV JIB100 – Jaíba 100* *⚙️🟥 🧰 Atividade cancelada: Preventiva Anual. > Devido", ("atividade_cancelada", "Preventiva Anual", None, None)),
    ("Entrada da 07:54 UFV São Pedro", ("entrada", None, "07:54", "São Pedro")),
    ("Saída UFV- Porteiras", ("saida", None, None, "Porteiras")),
    ("Entrada UFV GOY800 às 14:55", ("entrada", None, "14:55", "GOY800")),
    ("Entrada UFV PTY 100 13:02 Ryan", ("entrada", None, "13:02", "PTY 100")),
    ("Saída de corrente do inversor 3 zerada", None),
    ("*UFV GOY100* > Trackers liberados > Horário de término da atividade: 17h22min", None),
    ("*UFV ABC200 – X* *⚙️🧰 Atividade no transformador* > Inversores desligados", ("atividade_inicio", "Atividade no transformador", None, None)),
    ("*UFV ABC200 – X* *⚙️🟩 Atividade no transformador concluída* > Horário de término", ("atividade_fim", "Atividade no transformador", None, None)),
]:
    if coletor.classificar_manutencao(frase) != esperado:
        erros += 1
        print("✗ manutenção/presença:   ", frase, "→", coletor.classificar_manutencao(frase))
# atividade de manutenção não é ocorrência nem normalização
if coletor.classificar(coletor.sem_acento("*UFV GOY100 – GOY100* *⚙️🟩 Atividade concluída: Roçada*")) == "normal" and \
   coletor.classificar_manutencao("*UFV GOY100 – GOY100* *⚙️🟩 Atividade concluída: Roçada*") is None:
    erros += 1
total = 7 + 10 + 5 + len(DA_BAIXA) + len(NAO_DA_BAIXA) + len(NAO_E_OCORRENCIA) + len(E_OCORRENCIA) + 2
print(f"{total - erros}/{total} casos certos")
sys.exit(1 if erros else 0)
