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
- Branch avaliada: `main` (tags `entrega-final` e `v1.0`)

## Sistema e arquitetura

PlantSync é uma aplicação de rastreabilidade de lotes agrícolas. O frontend em JavaScript consome uma API FastAPI; o backend usa SQLAlchemy e SQLite. Sensores/placas comunicam leituras por rotas legadas autenticadas com chave de dispositivo, enquanto usuários usam a API v1 com token de sessão e contexto de empresa.

## Controles

### 2FA (TOTP)

- **Ameaça:** credencial de senha roubada ou reutilizada.
- **Controle:** TOTP RFC 6238; segredo cifrado em repouso com Fernet; códigos de recuperação armazenados como hashes e consumidos uma vez; token MFA temporário não serve como token de acesso; replay de TOTP é rejeitado.
- **Onde está implementado:**
  - [`back_end/security/totp_service.py`](../back_end/security/totp_service.py): geração e verificação do TOTP, anti-replay, cifra Fernet do segredo, códigos de recuperação com hash e token MFA temporário.
  - [`back_end/services/acessos.py`](../back_end/services/acessos.py): `fazer_login` exige o segundo fator quando o 2FA está ativo, `verificar_2fa_login` conclui o login e `sessao_autenticada` recusa o token MFA como token de acesso.
  - [`back_end/controllers/contas.py`](../back_end/controllers/contas.py): rotas `/api/v1/2fa/setup`, `/confirm`, `/verify-login`, `/status` e `/desativar`.
  - [`back_end/security/audit_log.py`](../back_end/security/audit_log.py): log de bloqueio com o código de missão (`[MISSAO:CP5TN0][BLOQUEIO][2FA]`).
  - [`front_end/js/produto.js`](../front_end/js/produto.js): tela de verificação do segundo fator no login.
- **Uso:** usuário autenticado solicita setup, cadastra a URI/QR em app autenticador e confirma um OTP; o frontend mostra os códigos de recuperação uma única vez. Login protegido exige verificação do segundo fator.
- **Teste:** [`testes/test_2fa_otp.py`](testes/test_2fa_otp.py) exercita o estado sem 2FA, ativação, ausência/erro de OTP, sucesso, replay, token MFA e recuperação descartável.
- **Limitação:** ativação é opcional por conta; não há política global que obrigue todas as contas a cadastrar 2FA.

#### Resultado

Evidência: [`evidencias/teste_2fa_CP5TN0.txt`](evidencias/teste_2fa_CP5TN0.txt). O ANTES e o DEPOIS estão na mesma execução: o script mede a conta antes de ativar o 2FA e depois de ativá-lo.

| | Situação | Resultado |
|---|---|---|
| **Antes** | Conta sem 2FA | `POST /api/v1/login` só com senha → `200`, sessão entregue direto (`[ANTES] Login com senha sem OTP aceito diretamente`). Quem tem a senha entra. |
| **Depois** | 2FA ativado | Login com senha → `200` com `mfa_required: true` e sem sessão. Sem OTP → `401`. OTP incorreto → `401`. OTP válido → `200`. Replay do mesmo OTP → `401`. `mfa_token` usado como token de acesso → `401`. Código de recuperação: 1º uso `200`, 2º uso `401`. Cada bloqueio gera um log `[MISSAO:CP5TN0][BLOQUEIO][2FA]` ou `[AUTH]`. |

### Isolamento multiempresa (IDOR)

- **Ameaça:** usuário acessa ou altera lote, sensor ou operação de outra empresa manipulando identificadores ou cabeçalhos.
- **Controle:** API v1 deriva identidade da sessão, valida o vínculo para `X-Empresa-ID` e verifica a empresa titular nos recursos protegidos.
- **Onde está implementado:**
  - [`back_end/services/acessos.py`](../back_end/services/acessos.py): `obter_contexto` e `id_empresa_solicitada` validam o `X-Empresa-ID` contra os vínculos ativos da conta. Sem vínculo, a resposta é `403`.
  - [`back_end/services/operacao_acesso.py`](../back_end/services/operacao_acesso.py): `lotes_visiveis` filtra os lotes pela empresa do contexto; `concessao`, `lote_acessivel` e `dono` exigem titularidade ou compartilhamento válido.
  - [`back_end/services/operacao_monitoramento.py`](../back_end/services/operacao_monitoramento.py): `sensor_da_empresa` confere a empresa titular do sensor.
  - [`back_end/services/operacao.py`](../back_end/services/operacao.py): `ambiente_da_empresa` confere a empresa titular do ambiente.
  - [`back_end/controllers/operacao.py`](../back_end/controllers/operacao.py): os schemas usam `extra="forbid"`, então campos como `empresa_id` no corpo da requisição são recusados.
  - [`back_end/security/audit_log.py`](../back_end/security/audit_log.py): log de bloqueio com o código de missão (`[MISSAO:CP5TN0][BLOQUEIO][IDOR]`).
  - Observação: [`back_end/security/ownership.py`](../back_end/security/ownership.py) tem um validador genérico (`validar_posse`), mas as rotas da API v1 não o usam. As checagens efetivas são as listadas acima.
- **Teste:** [`testes/test_idor.py`](testes/test_idor.py) cria duas empresas e tenta leitura, alteração, comando e vínculo cruzado; verifica também operações legítimas dos titulares. [`testes/test_idor_antes.py`](testes/test_idor_antes.py) roda os mesmos cenários e registra o que é aceito quando a checagem está desativada.
- **Limitação:** as rotas legadas de dispositivo usam chave de dispositivo e não o mesmo contexto de usuário/empresa. A equipe deve demonstrar o escopo protegido e explicar essa fronteira.

#### Resultado

Evidências da mesma rodada (26/11/2026): ANTES em [`evidencias/teste_idor_antes_CP5TN0.txt`](evidencias/teste_idor_antes_CP5TN0.txt) e DEPOIS em [`evidencias/teste_idor_CP5TN0.txt`](evidencias/teste_idor_CP5TN0.txt).

O User A pertence à Empresa A e ataca recursos da Empresa B:

| Cenário | Antes (checagem desativada) | Depois (controle ativo) |
|---|---|---|
| [1] Ler lote `PS-BETA99` da Empresa B | `200`, dados do lote vazados | `404` |
| [2] Alterar o lote da Empresa B | `200`, variedade alterada | `404` |
| [3] Comando `preparar` no lote da Empresa B | `200`, comando executado | `404` |
| [4] Vincular sensor da Empresa B | `200`, sensor vinculado | `404` |
| [5] `empresa_id` forjado no corpo | `400` (recusado pelo schema, independente da posse) | `400` |
| [6] `X-Empresa-ID` da Empresa B | `200`, contexto de administrador da Empresa B | `403` |
| [7]–[9] Operações legítimas dos titulares | `200` | `200` |

- **Antes:** 5 de 6 tentativas cruzadas aceitas, nenhum log de bloqueio.
- **Depois:** 6 de 6 bloqueadas, titulares sem impacto e um log `[MISSAO:CP5TN0][BLOQUEIO][IDOR]` para cada bloqueio de posse ou vínculo.

## Execução

Use banco isolado e segredos temporários. Não copie credenciais reais para os comandos, logs, arquivos de evidência ou Git. `.env.example` contém apenas nomes de variáveis. Os testes gravam no banco diretamente para preparar contas sintéticas, então a API e os testes precisam usar o **mesmo** `DATABASE_URL`, com caminho absoluto. Nunca aponte para o banco de produção (`back_end/plantsync.db`).

Terminal 1, API (a partir da raiz do repositório):

```bash
source back_end/.venv/bin/activate          # Windows: back_end\.venv\Scripts\activate
export DATABASE_URL="sqlite:///$PWD/back_end/plantsync_teste.db"   # Windows: sqlite:///C:/caminho/PlantSync/back_end/plantsync_teste.db
export PLANTSYNC_CODIGO_MISSAO=CP5TN0
export PLANTSYNC_TOTP_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
cd back_end
uvicorn app:app --host 127.0.0.1 --port 8000 2>&1 | tee ../api_teste.log
```

Terminal 2, testes do DEPOIS (a partir da raiz do repositório, sem `PYTHONPATH`):

```bash
source back_end/.venv/bin/activate
export DATABASE_URL="sqlite:///$PWD/back_end/plantsync_teste.db"   # mesmo valor do terminal 1
export PLANTSYNC_API_URL=http://127.0.0.1:8000
export PLANTSYNC_CODIGO_MISSAO=CP5TN0
python seguranca/testes/test_2fa_otp.py 2>&1 | tee seguranca/evidencias/teste_2fa_CP5TN0.txt
python seguranca/testes/test_idor.py 2>&1 | tee seguranca/evidencias/teste_idor_CP5TN0.txt
```

As linhas `[MISSAO:CP5TN0][BLOQUEIO]` aparecem no log da API (`api_teste.log`). Nas evidências versionadas, elas foram anexadas ao fim de cada arquivo. Apague `api_teste.log` e `plantsync_teste.db` depois da execução (`*.db` já é ignorado pelo Git).

### ANTES do IDOR

Para reproduzir o ANTES, desative a checagem de posse **apenas na cópia local** e reinicie a API. Pontos desativados na captura de 26/11/2026:

- `obter_contexto` (`services/acessos.py`): aceitar um `X-Empresa-ID` sem vínculo;
- `lotes_visiveis`, `concessao` e `dono` (`services/operacao_acesso.py`): não filtrar o lote pela empresa nem exigir titularidade;
- `sensor_da_empresa` (`services/operacao_monitoramento.py`): não comparar a empresa do sensor;
- `validar_posse` (`security/ownership.py`): retornar sem checar.

Com a API alterada no ar, rode:

```bash
python seguranca/testes/test_idor_antes.py 2>&1 | tee seguranca/evidencias/teste_idor_antes_CP5TN0.txt
```

Em seguida, reverta e confirme que o código voltou ao original **antes de qualquer commit**. O `checkout` descarta toda alteração local nesses diretórios, então não deixe outro trabalho pendente neles:

```bash
git checkout -- back_end/services back_end/security
git diff --exit-code -- back_end   # não pode mostrar nada
```

Depois rode o `test_idor.py` normal, com o banco recriado, para registrar o DEPOIS na mesma rodada. Contra a API sem alteração, `test_idor_antes.py` mostra todas as tentativas como BLOQUEADAS.

## Evidências

Todos os arquivos de [`evidencias/`](evidencias/) usam o código oficial `CP5TN0` no nome:

- [`teste_2fa_CP5TN0.txt`](evidencias/teste_2fa_CP5TN0.txt): 2FA, antes e depois na mesma execução (24/11/2026).
- [`teste_idor_antes_CP5TN0.txt`](evidencias/teste_idor_antes_CP5TN0.txt): IDOR antes, com a checagem desativada (26/11/2026).
- [`teste_idor_CP5TN0.txt`](evidencias/teste_idor_CP5TN0.txt): IDOR depois, com o controle ativo, na mesma rodada do antes (26/11/2026).
- [`ROTEIRO-VIDEOS.md`](evidencias/ROTEIRO-VIDEOS.md): roteiro dos vídeos `video_2fa_CP5TN0.mp4` e `video_idor_CP5TN0.mp4`.

As execuções usaram banco SQLite isolado, chave TOTP temporária e apenas dados sintéticos. Antes de versionar novas evidências, remova tokens, códigos TOTP e dados pessoais. Credenciais ou chaves que já tenham aparecido no histórico do Git devem ser rotacionadas.

## Arquivos

- [`modelo-ameacas.md`](modelo-ameacas.md): ativos, ameaças, controles e riscos remanescentes.
- [`uso-de-ia.md`](uso-de-ia.md): ferramentas usadas e revisão humana necessária.
- [`testes/`](testes/): scripts de validação automatizada.
- [`evidencias/`](evidencias/): saídas reais dos testes e roteiro dos vídeos.
