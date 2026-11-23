"""Converte uma cópia explícita do banco e confirma as contagens do histórico."""

import argparse
from contextlib import closing
from datetime import datetime
from pathlib import Path
import os
import sqlite3
import sys
from tempfile import NamedTemporaryFile


def salvar_backup(banco):
    horario = datetime.now().strftime("%Y%m%d-%H%M%S")
    with NamedTemporaryFile(
        prefix=f"{banco.stem}-antes-operacao-{horario}-", suffix=".db",
        dir=banco.parent, delete=False,
    ) as arquivo:
        destino = Path(arquivo.name)
    try:
        with closing(sqlite3.connect(banco.as_uri() + "?mode=ro", uri=True)) as origem:
            with closing(sqlite3.connect(destino)) as backup:
                origem.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise SystemExit("O backup não passou na verificação de integridade.")
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    return destino


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", required=True, type=Path)
    parser.add_argument("--empresa", required=True)
    args = parser.parse_args()
    banco = args.banco.resolve(strict=True)
    if not args.empresa.strip():
        parser.error("Informe a empresa que receberá o histórico.")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ["DATABASE_URL"] = "sqlite:///" + banco.as_posix()

    from config import CANAL_THINGSPEAK, PLANTSYNC_SENHA, PLANTSYNC_USUARIO
    from models.banco import Base, SessaoLocal, engine
    from models import contas, migracoes, operacao, tabelas  # noqa: F401
    from services.acessos import preparar_conta_inicial
    from services.migracao_operacional import migrar_legado

    if not PLANTSYNC_USUARIO or not PLANTSYNC_SENHA:
        raise SystemExit("Configure o usuário inicial e sua senha no ambiente local.")

    destino = salvar_backup(banco)

    Base.metadata.create_all(engine)
    with SessaoLocal() as sessao:
        empresa, conta = preparar_conta_inicial(
            sessao, PLANTSYNC_USUARIO, PLANTSYNC_SENHA, args.empresa.strip(),
        )
        if empresa.nome != args.empresa.strip():
            raise SystemExit(
                "A empresa solicitada difere da empresa inicial existente. "
                "Informe explicitamente o nome atual da empresa que receberá o histórico."
            )
        try:
            resumo = migrar_legado(sessao, empresa.id, conta.id, CANAL_THINGSPEAK)
            sessao.commit()
        except Exception:
            sessao.rollback()
            raise
    print("Migração confirmada:", resumo)
    print("Backup íntegro:", destino)


if __name__ == "__main__":
    main()
