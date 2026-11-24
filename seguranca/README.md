# Entrega de segurança — PlantSync

> **Entrega pendente de dados oficiais:** substituir `PREENCHER` pelo código de missão confirmado pelo professor e preencher o roster com nome e GitHub de cada integrante. Não usar o código de exemplos antigos como confirmação.

## Identificação

- Equipe: **PREENCHER nomes e usuários GitHub de todos os integrantes**
- Professor(a): **PREENCHER**
- Código oficial da missão: **PREENCHER**
- Branch avaliada: `masterv2`

## Sistema e arquitetura

PlantSync é uma aplicação de rastreabilidade de lotes agrícolas. O frontend em JavaScript consome uma API FastAPI; o backend usa SQLAlchemy e SQLite. Sensores/placas comunicam leituras por rotas legadas autenticadas com chave de dispositivo, enquanto usuários usam a API v1 com token de sessão e contexto de empresa.

## Controles

### 2FA (TOTP)

- **Ameaça:** credencial de senha roubada ou reutilizada.
- **Controle:** TOTP RFC 6238; segredo cifrado em repouso com Fernet; códigos de recuperação armazenados como hashes e consumidos uma vez; token MFA temporário não serve como token de acesso; replay de TOTP é rejeitado.
- **Uso:** usuário autenticado solicita setup, cadastra a URI/QR em app autenticador e confirma um OTP; o frontend mostra os códigos de recuperação uma única vez. Login protegido exige verificação do segundo fator.
- **Teste:** `testes/test_2fa_otp.py` exercita o estado sem 2FA, ativação, ausência/erro de OTP, sucesso, replay, token MFA e recuperação descartável.
- **Limitação:** ativação é opcional por conta; não há política global que obrigue todas as contas a cadastrar 2FA. O vídeo de uso deve ser gravado pela equipe.

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
export PLANTSYNC_CODIGO_MISSAO='CODIGO_OFICIAL'
python seguranca/testes/test_2fa_otp.py 2>&1 | tee seguranca/evidencias/teste_2fa_CODIGO_OFICIAL.txt
python seguranca/testes/test_idor.py 2>&1 | tee seguranca/evidencias/teste_idor_CODIGO_OFICIAL.txt
```

Troque `CODIGO_OFICIAL` pelo valor confirmado antes de executar e renomeie os arquivos de evidência com o mesmo código. Revise a saída e remova tokens, códigos TOTP e dados pessoais antes de versionar.

## Evidências e itens para concluir

Os arquivos de evidência automatizada existentes precisam ser reexecutados na versão final e revisados; não os trate como prova atual sem verificar a execução. Grave também os vídeos requeridos (cada um com até 90 segundos), mostrando o fluxo real na placa/dispositivo e o teste de cada controle. Nomeie os vídeos com o código oficial. Não simule placa nem invente resultados: documente no vídeo qualquer limitação do ambiente.

Antes da entrega:

1. preencher equipe, GitHub, professor e código oficial;
2. executar os dois testes e substituir as evidências por saídas reais sem segredos;
3. gravar e incluir os vídeos curtos de demonstração;
4. conferir histórico Git e rotacionar credenciais/chaves que já tenham sido publicadas;
5. criar a tag `entrega-final` após a revisão da equipe.

## Arquivos

- `modelo-ameacas.md`: ativos, ameaças, controles e riscos remanescentes.
- `uso-de-ia.md`: ferramentas usadas e revisão humana necessária.
- `testes/`: scripts de validação automatizada.
- `evidencias/`: saídas e gravações reais da equipe.
