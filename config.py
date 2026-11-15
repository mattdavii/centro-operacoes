# Configuração do Centro de Operações por usuário (cada instalação tem a sua).
# Fica em <pasta de dados>/config.json; o instalador cria com as respostas do usuário.
#   Linux:   ~/.local/share/centro-operacoes   (ou ~/.local/share/atendimentos, nas instalações antigas)
#   Windows: %LOCALAPPDATA%\CentroOperacoes
#   macOS:   ~/Library/Application Support/CentroOperacoes
import json, os, platform, shutil

REPOSITORIO = "mattdavii/centro-operacoes"  # de onde vêm as atualizações (PC e app Android)

PADRAO = {
    "nome_usuario": "",          # como te chamam nos grupos: "citou seu nome" procura isso (ex.: "Mateus")
    "apelidos": [],              # outros jeitos de te citar (ex.: ["Mateus Davi"])
    "organizacao": "",           # aparece no topo do painel (ex.: "O&M · GERAR")
    "wa": "",                    # caminho do comando wa do wa-app; vazio = procura sozinho
    "kmz": "",                   # KMZ das usinas para o mapa; vazio = <pasta de dados>/usinas.kmz
    "diario_py": "",             # opcional: integração com a planilha Diário de Chamados
    "diario_python": "",
    "pasta_relatorios": "",      # onde salvar a passagem de plantão; vazio = Documentos/Centro de Operações/Plantões
    "silencio_inicio": 20,       # horário sem som (celular e painel)
    "silencio_fim": 7,
    "porta": 47900,
    "corrigir_codigos": {},      # sigla digitada errado pelo COG -> a certa do KMZ (ex.: {"CAD": "CAC"})
    "kmz_preferir": {},          # código repetido no KMZ -> pasta (cliente) do ponto certo (ex.: {"CAC100": "Athon"})
}


def pasta_dados():
    if os.environ.get("CENTRO_DADOS"):  # outra pasta de dados (testes, ou mais de uma instalação no mesmo PC)
        return os.path.expanduser(os.environ["CENTRO_DADOS"])
    sistema = platform.system()
    if sistema == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "CentroOperacoes")
    if sistema == "Darwin":
        return os.path.expanduser("~/Library/Application Support/CentroOperacoes")
    antiga = os.path.expanduser("~/.local/share/atendimentos")  # instalação original (antes de virar app)
    return antiga if os.path.isdir(antiga) else os.path.expanduser("~/.local/share/centro-operacoes")


DADOS = pasta_dados()
ARQUIVO = os.path.join(DADOS, "config.json")


def carregar():
    c = dict(PADRAO)
    try:
        with open(ARQUIVO, encoding="utf-8") as f:
            c.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    except (OSError, ValueError):
        pass
    return c


def caminho(valor):
    return os.path.expanduser(os.path.expandvars(valor)) if valor else ""


def wa_comando():
    c = carregar()
    if c["wa"]:
        return caminho(c["wa"])
    for nome in ("wa", "wa.cmd", "wa.exe"):
        achado = shutil.which(nome)
        if achado:
            return achado
    return os.path.expanduser("~/.local/bin/wa")


def kmz():
    return caminho(carregar()["kmz"]) or os.path.join(DADOS, "usinas.kmz")


def documentos():
    """Pasta Documentos do usuário (no Linux em português costuma ser ~/Documentos)."""
    for nome in ("Documentos", "Documents"):
        p = os.path.expanduser(os.path.join("~", nome))
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def pasta_relatorios():
    return caminho(carregar()["pasta_relatorios"]) or os.path.join(documentos(), "Centro de Operações", "Plantões")


def diario():
    """(python, script) da integração com o Diário de Chamados, ou (None, None) se não houver."""
    c = carregar()
    py, script = caminho(c["diario_python"]), caminho(c["diario_py"])
    if script and os.path.isfile(script):
        return (py if py and os.path.isfile(py) else shutil.which("python3") or "python"), script
    return None, None
