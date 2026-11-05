"""
Configuracoes da API, lidas de variaveis de ambiente.

Para mudar algum valor localmente, copie .env.example para .env e edite.
O .env fica fora do git (RNF02): chave de API nunca vai para o repositorio.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def separar_origens(texto):
    """Transforma "a, b," em ["a", "b"]: tira espacos e itens vazios."""
    origens = []
    for origem in texto.split(","):
        origem = origem.strip()
        if origem:
            origens.append(origem)
    return origens


PASTA_BACKEND = os.path.dirname(os.path.abspath(__file__))

# Banco SQLite em arquivo dentro de back_end/. Para usar PostgreSQL, basta
# trocar a URL (ex.: postgresql://usuario:senha@localhost/plantsync).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(PASTA_BACKEND, "plantsync.db"),
)

CANAL_THINGSPEAK = int(os.getenv("CANAL_THINGSPEAK", "3493443"))

# So e necessaria se o canal deixar de ser publico.
CHAVE_LEITURA_THINGSPEAK = os.getenv("CHAVE_LEITURA_THINGSPEAK")

# Unico usuario do sistema; nao ha senha padrao. Sem as duas, ninguem consegue entrar.
PLANTSYNC_USUARIO = os.getenv("PLANTSYNC_USUARIO")
PLANTSYNC_SENHA = os.getenv("PLANTSYNC_SENHA")

# Chave da placa para buscar a faixa do lote. Sem ela, GET /api/dispositivo/faixa responde 503.
PLANTSYNC_CHAVE_DISPOSITIVO = os.getenv("PLANTSYNC_CHAVE_DISPOSITIVO")

# Enderecos do painel web que podem chamar a API pelo navegador.
CORS_ORIGENS = separar_origens(os.getenv(
    "CORS_ORIGENS",
    "http://localhost:5500,http://127.0.0.1:5500",
))
