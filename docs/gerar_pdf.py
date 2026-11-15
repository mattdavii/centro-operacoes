#!/usr/bin/env python3
# Gera docs/Centro-de-Operacoes.pdf: guia de instalação e uso, com QR do APK (sempre a última versão) e do repositório.
#   .venv-docs/bin/python docs/gerar_pdf.py        (precisa de qrcode e reportlab; o publicar.sh roda sozinho)
import io, os, sys
import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
import config  # noqa: E402

REPO = f"https://github.com/{config.REPOSITORIO}"
APK = f"{REPO}/releases/latest/download/CentroOperacoes.apk"
VERSAO = open(os.path.join(RAIZ, "VERSAO")).read().strip()

# fontes com acentos (DejaVu, se houver; senão Helvetica)
FONTE, NEGRITO, MONO = "Helvetica", "Helvetica-Bold", "Courier"
for nome, arq in (("Texto", "DejaVuSans.ttf"), ("TextoNegrito", "DejaVuSans-Bold.ttf"), ("Mono", "DejaVuSansMono.ttf")):
    for pasta in ("/usr/share/fonts/TTF", "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu"):
        if os.path.exists(os.path.join(pasta, arq)):
            pdfmetrics.registerFont(TTFont(nome, os.path.join(pasta, arq)))
            break
if "Texto" in pdfmetrics.getRegisteredFontNames():
    FONTE, NEGRITO = "Texto", "TextoNegrito"
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("Texto", normal="Texto", bold="TextoNegrito", italic="Texto", boldItalic="TextoNegrito")
if "Mono" in pdfmetrics.getRegisteredFontNames():
    MONO = "Mono"

AZUL, ESCURO, CINZA, VERDE, VERMELHO = (colors.HexColor(c) for c in ("#1d6fb8", "#0b1530", "#5b6478", "#1e8a52", "#c1121f"))
st = {
    "titulo": ParagraphStyle("titulo", fontName=NEGRITO, fontSize=26, leading=31, textColor=ESCURO, spaceAfter=4),
    "sub": ParagraphStyle("sub", fontName=FONTE, fontSize=12, leading=16, textColor=CINZA, spaceAfter=14),
    "h1": ParagraphStyle("h1", fontName=NEGRITO, fontSize=16, leading=20, textColor=ESCURO, spaceBefore=10, spaceAfter=8, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName=NEGRITO, fontSize=12, leading=16, textColor=AZUL, spaceBefore=8, spaceAfter=4, keepWithNext=1),
    "p": ParagraphStyle("p", fontName=FONTE, fontSize=10, leading=14.5, textColor=colors.HexColor("#1f2433"), spaceAfter=6),
    "li": ParagraphStyle("li", fontName=FONTE, fontSize=10, leading=14.5, leftIndent=14, bulletIndent=3, spaceAfter=3),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=8.6, leading=12, backColor=colors.HexColor("#f2f4f8"),
                           borderPadding=6, leftIndent=4, rightIndent=4, spaceBefore=4, spaceAfter=10),
    "qr": ParagraphStyle("qr", fontName=NEGRITO, fontSize=10, leading=13, alignment=TA_CENTER, textColor=ESCURO),
    "qrp": ParagraphStyle("qrp", fontName=FONTE, fontSize=8, leading=10, alignment=TA_CENTER, textColor=CINZA),
    "nota": ParagraphStyle("nota", fontName=FONTE, fontSize=9, leading=13, textColor=CINZA, spaceAfter=6),
}


def qr(url, tam=48 * mm):
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=tam, height=tam)


def lista(itens):
    return [Paragraph(i, st["li"], bulletText="•") for i in itens]


def passos(itens):
    return [Paragraph(i, st["li"], bulletText=f"{n}.") for n, i in enumerate(itens, 1)]


def codigo(texto):
    return Paragraph(texto.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), st["code"])


def tabela(linhas, larguras):
    t = Table([[Paragraph(c, st["p"]) for c in l] for l in linhas], colWidths=larguras)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef8")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d2e3")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return t


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONTE, 8)
    canvas.setFillColor(CINZA)
    canvas.drawString(18 * mm, 10 * mm, f"Centro de Operações · v{VERSAO} · {REPO.replace('https://', '')}")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"página {doc.page}")
    canvas.restoreState()


def main():
    saida = os.path.join(AQUI, "Centro-de-Operacoes.pdf")
    doc = SimpleDocTemplate(saida, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title="Centro de Operações: instalação e uso",
                            author="Centro de Operações", subject="Guia de instalação e uso")
    h = []
    # ---------- capa ----------
    h += [Spacer(1, 8 * mm), Paragraph("◉ Centro de Operações", st["titulo"]),
          Paragraph(f"Plantão das usinas sobre o WhatsApp (wa-app) · guia de instalação e uso · versão {VERSAO}", st["sub"])]
    h.append(Paragraph(
        "Painel que lê os grupos do WhatsApp pelo <b>wa-app</b> (só leitura, nunca envia nada) e mostra as "
        "<b>ocorrências das usinas</b>, as <b>conversas que esperam você</b>, o <b>mapa</b>, os <b>indicadores</b> e o "
        "<b>relatório de passagem de plantão</b>. No celular Android, um app toca o <b>alarme</b> quando surge uma "
        "ocorrência crítica.", st["p"]))
    h.append(Spacer(1, 8 * mm))
    capa = Table([[qr(APK), qr(REPO)],
                  [Paragraph("App Android (última versão)", st["qr"]), Paragraph("Projeto e instruções", st["qr"])],
                  [Paragraph(APK.replace("https://", ""), st["qrp"]), Paragraph(REPO.replace("https://", ""), st["qrp"])]],
                 colWidths=[85 * mm, 85 * mm])
    capa.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("BOX", (0, 0), (0, -1), 0.6, colors.HexColor("#c9d2e3")),
                              ("BOX", (1, 0), (1, -1), 0.6, colors.HexColor("#c9d2e3")),
                              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    h.append(capa)
    h.append(Spacer(1, 8 * mm))
    h.append(Paragraph("O QR do app aponta sempre para a <b>versão mais nova</b> publicada; não é preciso trocar este PDF "
                       "quando sair atualização.", st["nota"]))
    h.append(Paragraph("<b>Precisa ter:</b> wa-app instalado e conectado ao WhatsApp · Python 3.9+ e git · Google Chrome ou "
                       "Microsoft Edge · Tailscale no PC e no celular (mesma conta) · celular Android (iPhone não é suportado).",
                       st["p"]))
    h.append(PageBreak())

    # ---------- instalação no PC ----------
    h.append(Paragraph("1. Instalar no PC (Linux ou Windows)", st["h1"]))
    h.append(Paragraph("Jeito mais fácil: pedir ao Claude", st["h2"]))
    h.append(Paragraph("No <b>Claude Code</b>, no PC onde o wa-app está instalado, cole (trocando nome e equipe):", st["p"]))
    h.append(codigo(f"Instale o Centro de Operações deste repositório no meu PC: {REPO}\n"
                    "Siga o INSTALAR.md (seção \"Para o Claude\"). Meu nome nos grupos é <SEU NOME>\n"
                    "e minha equipe é <SUA EQUIPE>."))
    h.append(Paragraph("O Claude confere os requisitos, instala, liga o serviço (que passa a subir junto com o PC) e cria o "
                       "atalho <b>Centro de Operações</b> no menu e na área de trabalho.", st["p"]))
    h.append(Paragraph("Ou à mão: Linux", st["h2"]))
    h.append(codigo(f"git clone {REPO} ~/centro-operacoes\n"
                    "bash ~/centro-operacoes/instalar.sh --nome \"Seu Nome\" --organizacao \"Sua Equipe\""))
    h.append(Paragraph("Ou à mão: Windows (PowerShell)", st["h2"]))
    h.append(codigo(f"git clone {REPO} $env:USERPROFILE\\centro-operacoes\n"
                    "powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\\centro-operacoes\\instalar.ps1 -Nome \"Seu Nome\""))
    h.append(Paragraph("No Windows, liberar o celular no firewall precisa de PowerShell <b>como administrador</b>; se o "
                       "instalador avisar, rode o comando que ele mostra.", st["nota"]))
    h.append(Paragraph("Opcional: KMZ das usinas", st["h2"]))
    h.append(Paragraph("Para o mapa, passe o KMZ das suas usinas no instalador (<font face='%s'>--kmz arquivo.kmz</font>) ou "
                       "copie para a pasta de dados com o nome <b>usinas.kmz</b>. Pontos com o código da usina "
                       "(ex.: PTY100) casam sozinhos com os avisos do COG; a pasta \"Técnicos\" vira a camada de técnicos, "
                       "usada para mostrar os mais próximos de cada ocorrência." % MONO, st["p"]))

    # ---------- celular ----------
    h.append(Paragraph("2. Celular (Android)", st["h1"]))
    h += passos([
        "Instale o <b>Tailscale</b> no celular e entre com a <b>mesma conta</b> do PC.",
        "Instale o app pelo QR da capa (permita \"instalar apps desta fonte\").",
        "No PC, abra o Centro de Operações e clique em <b>Conectar celular</b>. Aponte a câmera do celular para o QR, "
        "toque no link e depois em <b>CONECTAR ESTE CELULAR</b>.",
        "Permita as <b>notificações</b> e \"<b>não otimizar bateria</b>\" (sem isso o Android pode pausar os alarmes).",
        "No PC, clique em <b>Testar alarme</b>: o celular deve tocar em até 1 minuto.",
    ])
    h.append(Paragraph("O QR de conexão dá acesso ao seu painel: não mostre para outras pessoas. O acesso só funciona pelo "
                       "Tailscale e com essa senha; ninguém de fora consegue entrar.", st["nota"]))
    h.append(PageBreak())

    # ---------- uso ----------
    h.append(Paragraph("3. Usando o painel", st["h1"]))
    h.append(tabela([
        ["Parte", "O que mostra / o que fazer"],
        ["<b>Ocorrências</b>", "Avisos de desarme, trip, emergencial (crítica) e falha, comunicação, alarme (alerta), juntados por "
         "usina. Clique para ver a conversa inteira, os técnicos mais próximos e o mapa."],
        ["<b>CIENTE</b>", "Para o alarme daquela ocorrência (ela continua aberta)."],
        ["<b>ENCERRAR / REABRIR</b>", "Fecha à mão o que foi resolvido sem aviso no grupo; REABRIR desfaz qualquer baixa errada."],
        ["<b>Baixa automática</b>", "Só com normalização confirmada: o \"Normalização\" do COG, \"usina religada\", \"pode encerrar a OS\". Pergunta, "
         "negação, intenção ou \"parece que voltou\" não fecham. Nada fecha por tempo: depois de 6 h sem novidade, a "
         "ocorrência pergunta \"Continua com o mesmo status?\" (CONTINUAR ACOMPANHANDO ou JÁ FOI RESOLVIDA)."],
        ["<b>Em campo · Manutenções</b>", "Quem está em qual usina agora (pelas mensagens \"Entrada em UFV ...\" / \"Saída\") e as "
         "atividades do COG do dia (em andamento, concluída, cancelada). Aparecem também no mapa, na linha do tempo (barras azuis), "
         "no relatório do plantão e nos indicadores."],
        ["<b>Durante manutenção</b>", "Ocorrência que começa com uma atividade em andamento na mesma usina ganha a etiqueta e não "
         "toca alarme no celular. Se a atividade acabar e a usina continuar com problema, o alarme volta."],
        ["<b>Aguardando você</b>", "Privados em que a última mensagem não é sua e grupos em que te marcaram ou citaram seu nome. "
         "Respondi / Resolvido / Lembrar / Ignorar limpam a lista."],
        ["<b>Linha do tempo</b>", "Cada ocorrência do aviso até a normalização: vê de relance o que está aberto há mais tempo."],
        ["<b>Mapa</b>", "Usinas por situação (vermelho, amarelo, verde), técnicos e bases. Escuro ou satélite."],
        ["<b>Indicadores</b>", "24 h / 7 / 30 dias, por cliente: ocorrências por dia, usinas reincidentes, tempo até normalizar, "
         "tipos de falha."],
        ["<b>Plantão</b>", "INICIAR PLANTÃO e FINALIZAR PLANTÃO. Ao finalizar, o relatório de passagem é gerado e salvo "
         "(PDF e texto pronto para o WhatsApp). RELATÓRIO ATÉ AGORA mostra o parcial."],
        ["<b>Silêncio</b>", "Das 20h às 7h nada toca (celular e PC); as notificações chegam mudas. Ajustável no config.json."],
    ], [38 * mm, 136 * mm]))
    h.append(Spacer(1, 6))
    h.append(Paragraph("No celular", st["h2"]))
    h += lista([
        "Crítica nova: <b>alarme</b> (e repete a cada 5 min no plantão até você dar CIENTE). Alerta ou marcação: notificação normal.",
        "PC ou WhatsApp do PC fora do ar por 10 min: aviso (alarme no plantão).",
        "Sem conexão com o PC, o app mostra os últimos dados guardados.",
    ])

    # ---------- atualizações ----------
    h.append(Paragraph("4. Atualizações", st["h1"]))
    h += lista([
        "<b>PC:</b> aparece a faixa \"Nova versão do Centro de Operações\" com <b>ATUALIZAR AGORA</b> (baixa e reinicia sozinho).",
        "<b>Celular:</b> a tela se atualiza sozinha. Quando o app muda, chega a notificação \"Nova versão\": toque e instale.",
    ])
    h.append(Paragraph("5. Privacidade", st["h1"]))
    h.append(Paragraph("Tudo roda no seu PC. O painel só lê o WhatsApp pelo wa-app e nunca envia mensagem. Configuração, senha "
                       "do celular, histórico e relatórios ficam na pasta de dados do seu PC (Linux "
                       "<font face='%s'>~/.local/share/centro-operacoes</font>, Windows "
                       "<font face='%s'>%%LOCALAPPDATA%%\\CentroOperacoes</font>), com backup diário às 03:30. Nada disso vai "
                       "para o GitHub." % (MONO, MONO), st["p"]))
    doc.build(h, onFirstPage=rodape, onLaterPages=rodape)
    print("PDF:", saida)


if __name__ == "__main__":
    main()
