# Estrutura do projeto

Mapa rápido das pastas do repositório.

| Pasta | Conteúdo |
|---|---|
| `back_end/` | API em Python: `controllers/` (rotas), `services/` (regras), `models/` (banco), `security/` (2FA, auditoria, posse de recursos), `scripts/` (migração) e `tests/` (pytest). |
| `front_end/` | Painel web (HTML, CSS e JS), páginas públicas de lote/QR, mapas e bibliotecas em `vendor/`. |
| `hardware/plantsync-edge/` | Firmware do ESP32 (`main.ino`), simulação Wokwi e modelo de credenciais (`credentials.h.example`). |
| `analytics/` | Script de análise exploratória (`eda_plantsync.py`). `data/` e `outputs/` guardam arquivos gerados localmente e não são versionados. |
| `seguranca/` | Modelo de ameaças, uso de IA, testes de segurança (2FA e IDOR) e evidências. |
| `docs/` | Documentação: checkpoint, contrato da API, modelo operacional e imagens. |
| `api/` | Coleção Postman para testar a API. |
| `tools/` | Servidores locais para o painel e para o QR na rede local. |

## Fluxo de dados

sensor → ESP32 → ThingSpeak → API → painel → QR

## Onde começar

- Rodar o projeto: [README.md](../README.md)
- Contribuir: [CONTRIBUTING.md](../CONTRIBUTING.md)
- API: [api-contrato.md](api-contrato.md) e [API-OPERACAO.md](API-OPERACAO.md)
