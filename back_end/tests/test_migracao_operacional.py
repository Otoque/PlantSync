"""A conversão preserva o histórico e pode ser repetida ou desfeita."""

from datetime import datetime, timedelta
from pathlib import Path
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.banco import Base
from models.contas import Conta, Empresa
from models.migracoes import RegistroMigracao
from models.operacao import FonteSensor, LeituraFonte, LoteOperacional, Permanencia
from models.tabelas import Dispositivo, Leitura, Lote
from services.acessos import preparar_conta_inicial
from services.frutas import cadastrar_frutas_iniciais
from services.migracao_operacional import migrar_legado


@pytest.fixture
def origem_migracao():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    with fabrica() as sessao:
        cadastrar_frutas_iniciais(sessao)
        empresa = Empresa(nome="Empresa da migração", ativo=True)
        conta = Conta(nome="operador", sal="00" * 16, senha_hash="hash-de-teste", ativo=True)
        sessao.add_all([empresa, conta])
        sessao.flush()
        inicio = datetime(2026, 11, 16, 17)
        fim = inicio + timedelta(hours=2)
        sessao.add(Lote(
            id=4, fruta_id="uva", produtor="Produtor", origem="Petrolina",
            destino="Recife", tipo_destino="mercado_interno", inicio=inicio, fim=fim,
            codigo_publico="codigo-publico-teste", token_laudo="segredo-sintetico-laudo",
            temp_min_c=0, temp_max_c=2, umidade_min_pct=85, umidade_max_pct=95,
        ))
        sessao.add_all([
            Leitura(entry_id=1, data_hora=inicio, temperatura_c=1.5),
            Leitura(entry_id=2, data_hora=fim, temperatura_c=1.8),
        ])
        sessao.commit()
        yield sessao, empresa.id, conta.id
    engine.dispose()


def test_migracao_preserva_lotes_leituras_e_amostra_do_encerramento(origem_migracao):
    sessao, empresa_id, conta_id = origem_migracao
    resumo = migrar_legado(sessao, empresa_id, conta_id, 3564689)
    sessao.commit()

    assert resumo == {"lotes": 1, "leituras": 2, "fontes": 1, "empresa_id": empresa_id}
    convertido = sessao.get(LoteOperacional, 4)
    assert convertido.codigo_publico == "codigo-publico-teste"
    assert convertido.legado_id == 4
    assert convertido.fase == 3
    assert sessao.query(Lote).count() == 1
    assert sessao.query(Leitura).count() == 2
    assert sessao.query(LeituraFonte).count() == 2
    permanencia = sessao.query(Permanencia).one()
    assert sessao.query(LeituraFonte).filter(
        LeituraFonte.data_hora >= permanencia.inicio,
        LeituraFonte.data_hora < permanencia.fim,
    ).count() == 2


def test_repetir_migracao_nao_duplica_e_nao_troca_empresa(origem_migracao):
    sessao, empresa_id, conta_id = origem_migracao
    primeiro = migrar_legado(sessao, empresa_id, conta_id, 3564689)
    sessao.commit()
    assert migrar_legado(sessao, empresa_id, conta_id, 3564689) == primeiro
    assert sessao.query(RegistroMigracao).count() == 1
    assert sessao.query(LeituraFonte).count() == 2
    with pytest.raises(ValueError, match="outra empresa"):
        migrar_legado(sessao, empresa_id + 1, conta_id, 3564689)


def test_migracao_admite_rollback_sem_apagar_origem(origem_migracao):
    sessao, empresa_id, conta_id = origem_migracao
    migrar_legado(sessao, empresa_id, conta_id, 3564689)
    sessao.rollback()
    assert sessao.query(RegistroMigracao).count() == 0
    assert sessao.query(LoteOperacional).count() == 0
    assert sessao.query(LeituraFonte).count() == 0
    assert sessao.query(Lote).count() == 1
    assert sessao.query(Leitura).count() == 2
    assert migrar_legado(sessao, empresa_id, conta_id, 3564689)["lotes"] == 1


def test_migracao_aceita_placas_legadas_com_nomes_repetidos(origem_migracao):
    sessao, empresa_id, conta_id = origem_migracao
    sessao.add_all([
        Dispositivo(nome="Placa padrão", canal=101),
        Dispositivo(nome="Placa padrão", canal=102),
    ])
    sessao.commit()
    assert migrar_legado(sessao, empresa_id, conta_id, 3564689)["fontes"] == 3
    sessao.commit()
    fontes = sessao.query(FonteSensor).all()
    assert {fonte.canal for fonte in fontes} == {3564689, 101, 102}
    assert len({fonte.nome for fonte in fontes}) == 3


def test_cli_recusa_destino_diferente_do_bootstrap(tmp_path):
    banco = tmp_path / "operacao.db"
    engine = create_engine("sqlite:///" + banco.as_posix())
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as sessao:
        preparar_conta_inicial(sessao, "operador-cli", "senha-cli-sintetica-2026", "Empresa A")
        sessao.commit()
    engine.dispose()
    ambiente = {
        **os.environ,
        "PYTHON_DOTENV_DISABLED": "1",
        "PLANTSYNC_USUARIO": "operador-cli",
        "PLANTSYNC_SENHA": "senha-cli-sintetica-2026",
    }
    backend = Path(__file__).resolve().parents[1]
    resultado = subprocess.run(
        [sys.executable, "-B", str(backend / "scripts/migrar_operacao.py"),
         "--banco", str(banco), "--empresa", "Empresa B"],
        cwd=backend, env=ambiente, capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode != 0
    assert "empresa solicitada difere" in resultado.stderr
    engine = create_engine("sqlite:///" + banco.as_posix())
    with sessionmaker(bind=engine)() as sessao:
        assert sessao.query(RegistroMigracao).count() == 0
        assert sessao.query(Empresa).one().nome == "Empresa A"
    engine.dispose()
