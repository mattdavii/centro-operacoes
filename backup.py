#!/usr/bin/env python3
# Cópia diária das configurações e dados do Centro de Operações (Linux: timer do systemd; Windows: tarefa agendada).
# Inclui a senha de acesso do celular e o histórico. Ficam as 14 últimas cópias, em
# Documentos/Centro de Operações/backups (ou config.json: "pasta_backup").
import datetime as dt, os, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PROJETO = os.path.dirname(os.path.abspath(__file__))
IGNORAR = {"dist", "build", "__pycache__", ".git"}


def main():
    destino = config.caminho(config.carregar().get("pasta_backup", "")) or \
        os.path.join(config.documentos(), "Centro de Operações", "backups")
    os.makedirs(destino, exist_ok=True)
    try:
        os.chmod(destino, 0o700)
    except OSError:
        pass
    arq = os.path.join(destino, dt.date.today().isoformat() + ".zip")
    tmp = arq + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, rotulo in ((config.DADOS, "dados"), (PROJETO, "projeto")):
            for pasta, subpastas, arquivos in os.walk(raiz):
                subpastas[:] = [s for s in subpastas if s not in IGNORAR]
                for nome in arquivos:
                    p = os.path.join(pasta, nome)
                    z.write(p, os.path.join(rotulo, os.path.relpath(p, raiz)))
    os.replace(tmp, arq)
    try:
        os.chmod(arq, 0o600)
    except OSError:
        pass
    for velho in sorted(f for f in os.listdir(destino) if f.endswith(".zip"))[:-14]:
        os.remove(os.path.join(destino, velho))
    print(f"backup: {arq} ({os.path.getsize(arq) // 1024} KB)")


if __name__ == "__main__":
    main()
