# Entrega de segurança — PlantSync

> Código da missão e roster fornecidos pela equipe; perfis conforme o histórico do repositório ou confirmação da equipe.

## Identificação

- Equipe:
  - Davi Clemente — [@cldavii](https://github.com/cldavii)
  - Nicolas Tavares — [@Otoque](https://github.com/Otoque), confirmado pelo commit inicial do repositório ([commit](https://github.com/Otoque/PlantSync/commit/dcb6fd8e9d71bc032a85e08f353253dd503a00a5))
  - Pedro Valença — [@pedrohmvalenca](https://github.com/pedrohmvalenca)
  - Jorge Figueredo — [@Jorgefigueredoo](https://github.com/Jorgefigueredoo)
  - Ygor Sampaio — [@ygorsampaio](https://github.com/ygorsampaio)
- Professor: Ronierison Maciel
- Código oficial da missão: `CP5TN0`
- Branch avaliada: `masterv2`

## Sistema e arquitetura

PlantSync é uma aplicação de rastreabilidade de lotes agrícolas. O frontend em JavaScript consome uma API FastAPI; o backend usa SQLAlchemy e SQLite. Sensores/placas comunicam leituras por rotas legadas autenticadas com chave de dispositivo, enquanto usuários usam a API v1 com token de sessão e contexto de empresa.

## Controles

### 2FA (TOTP)

- **Ameaça:** credencial de senha roubada ou reutilizada.
- **Controle:** TOTP RFC 6238; segredo cifrado em repouso com Fernet; códigos de recuperação armazenados como hashes e consumidos uma vez; token MFA temporário não serve como token de acesso; replay de TOTP é rejeitado.
- **Uso:** usuário autenticado solicita setup, cadastra a URI/QR em app autenticador e confirma um OTP; o frontend mostra os códigos de recuperação uma única vez. Login protegido exige verificação do segundo fator.
- **Teste:** `testes/test_2fa_otp.py` exercita o estado sem 2FA, ativação, ausência/erro de OTP, sucesso, replay, token MFA e recuperação descartável.
- **Limitação:** ativação é opcional por conta; não há política global que obrigue todas as contas a cadastrar 2FA.

### Isolamento multiempresa (IDOR)

- **Ameaça:** usuário acessa ou altera lote, sensor ou operação de outra empresa manipulando identificadores ou cabeçalhos.
- **Controle:** API v1 deriva identidade da sessão, valida o vínculo para `X-Empresa-ID` e verifica a empresa titular nos recursos protegidos.
- **Teste:** `testes/test_idor.py` cria duas empresas e tenta leitura, alteração, comando e vínculo cruzado; verifica também operações legítimas dos titulares.
- **Limitação:** as rotas legadas de dispositivo usam chave de dispositivo e não o mesmo contexto de usuário/empresa. A equipe deve demonstrar o escopo protegido e explicar essa fronteira.

## Execução

Use banco isolado e segredos temporários. Não copie credenciais reais para os comandos, logs, arquivos de evidência ou Git. Configure no ambiente local `DATABASE_URL`, `PLANTSYNC_TOTP_KEY` (chave Fernet), `PLANTSYNC_CODIGO_MISSAO` (código oficial), `PLANTSYNC_TOTP_WINDOW` e credenciais de teste. `.env.example` contém apenas nomes de variáveis.

Em um terminal, inicie a API com esse ambiente configurado, por exemplo:

```bash
cd back_end
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8000
```

Em outro terminal, ative o mesmo ambiente e execute:

```bash
cd back_end
source .venv/bin/activate
export PLANTSYNC_API_URL=http://127.0.0.1:8000
export PLANTSYNC_CODIGO_MISSAO='CP5TN0'
python seguranca/testes/test_2fa_otp.py 2>&1 | tee seguranca/evidencias/teste_2fa_CP5TN0.txt
python seguranca/testes/test_idor.py 2>&1 | tee seguranca/evidencias/teste_idor_CP5TN0.txt
```

O código oficial `CP5TN0` já está configurado nos comandos. Confira os resultados, mantenha o código nos nomes dos arquivos e remova tokens, códigos TOTP e dados pessoais antes de versionar.

## Evidências e itens para concluir

Os testes automatizados foram executados em 24/11/2026 contra o backend local, com banco e chave TOTP temporários. As saídas aprovadas estão em `evidencias/teste_2fa_CP5TN0.txt` e `evidencias/teste_idor_CP5TN0.txt`; os arquivos antigos com outro código foram mantidos como registros anteriores.

Antes da entrega:

2. revisar as evidências atuais e garantir que não contenham segredos;
4. conferir histórico Git e rotacionar credenciais/chaves que já tenham sido publicadas;
5. criar a tag `entrega-final` após a revisão da equipe.

## Arquivos

- `modelo-ameacas.md`: ativos, ameaças, controles e riscos remanescentes.
- `uso-de-ia.md`: ferramentas usadas e revisão humana necessária.
- `testes/`: scripts de validação automatizada.
- `evidencias/`: saídas reais dos testes.
