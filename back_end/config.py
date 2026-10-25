"""
Configuracoes da API, lidas de variaveis de ambiente.

Para mudar algum valor localmente, copie .env.example para .env e edite.
O .env fica fora do git (RNF02): chave de API nunca vai para o repositorio.
"""

import os

from dotenv import load_dotenv

load_dotenv()

PASTA_BACKEND = os.path.dirname(os.path.abspath(__file__))

# Banco SQLite em arquivo dentro de back_end/. Para usar PostgreSQL, basta
# trocar a URL (ex.: postgresql://usuario:senha@localhost/plantsync).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(PASTA_BACKEND, "plantsync.db"),
)

CANAL_THINGSPEAK = int(os.getenv("CANAL_THINGSPEAK", "3493443"))

# So e necessaria se o canal deixar de ser publico.
THINGSPEAK_READ_API_KEY = os.getenv("THINGSPEAK_READ_API_KEY")

# Enderecos do painel web que podem chamar a API pelo navegador.
CORS_ORIGENS = os.getenv(
    "CORS_ORIGENS",
    "http://localhost:5500,http://127.0.0.1:5500",
).split(",")
