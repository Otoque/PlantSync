# PlantSync (masterv2) — Controles de Segurança: 2FA e Proteção contra IDOR

Este diretório consolida a documentação técnica, os testes automatizados e as evidências de validação dos controles obrigatórios de segurança implementados no backend do PlantSync na branch `masterv2` (arquitetura multiempresa em FastAPI + SQLAlchemy + SQLite).

**Código de Missão:** `K7Q2M9` (ou valor definido via variável de ambiente `PLANTSYNC_CODIGO_MISSAO`).

---

## 1. Visão Geral dos Controles Implementados

### 1.1. Autenticação de Dois Fatores (2FA com PyOTP + Fernet)
- **Algoritmo e Padrão:** TOTP (Time-based One-Time Password - RFC 6238), implementado com a biblioteca `pyotp` (janela padrão de 30 segundos, configurável via `PLANTSYNC_TOTP_WINDOW`).
- **Criptografia em Repouso:** O segredo base32 gerado pelo `pyotp.random_base32()` é cifrado com `cryptography.fernet.Fernet` utilizando a chave simétrica de 32 bytes configurada em `PLANTSYNC_TOTP_KEY` antes de ser persistido na tabela `contas`.
- **Códigos de Recuperação Descartáveis:** Durante o setup, 8 códigos de uso único (formato `XXXX-XXXX`) são gerados com `secrets.token_hex`. O banco armazena exclusivamente o hash SHA-256 de cada código. Ao ser utilizado, o código é marcado com timestamp UTC (`usado_em`), bloqueando reutilizações futuras.
- **Proteção Anti-Replay:** O servidor rastreia o último intervalo de tempo (`totp_last_timestep`) em que um código foi autenticado com sucesso. Caso o mesmo token TOTP seja reenviado dentro do mesmo ciclo de 30 segundos, a requisição é rejeitada com 401 Unauthorized e o bloqueio é registrado na auditoria.
- **Token MFA Temporário:** Se a conta possuir 2FA ativo, a senha correta não retorna token de acesso, mas sim `{"mfa_required": True, "mfa_token": "psm_..."}` válido por apenas 5 minutos na tabela `sessoes_mfa_conta`. A tentativa de utilizar `mfa_token` como token de acesso direto em endpoints protegidos é sumariamente rejeitada (401) e auditada.
- **Endpoints de 2FA:**
  - `POST /api/v1/2fa/setup`: Gera segredo cifrado, `provisioning_uri` (para geração de QR Code no frontend) e lista de códigos de recuperação (exibidos apenas uma vez).
  - `POST /api/v1/2fa/confirm`: Valida código OTP de 6 dígitos para efetivar a ativação do 2FA na conta.
  - `POST /api/v1/2fa/verify-login`: Recebe `mfa_token` e valida `otp_code` ou `recovery_code`, emitindo o token final de sessão (`pss_...`).
  - `GET /api/v1/2fa/status`: Informa se o 2FA está ativo na conta do usuário autenticado.
  - `POST /api/v1/2fa/desativar`: Permite a desativação controlada do segundo fator.

### 1.2. Proteção contra IDOR (Insecure Direct Object References)
- **Isolamento Estrito por Posse e Empresa:** O servidor nunca confia em parâmetros de identificação de usuário ou empresa (`user_id`, `empresa_id`, `owner_id`) enviados no corpo ou na query das requisições.
- **Extração Segura de Identidade:** A organização e as permissões são obtidas exclusivamente da sessão autenticada no servidor (`acessos.obter_contexto`), validando o cabeçalho `X-Empresa-ID` contra os vínculos legítimos do usuário (`vinculos_conta`).
- **Validação de Propriedade do Recurso:**
  - **Lotes Operacionais (`/api/v1/lotes/{codigo}`):** Validação por `lote_acessivel()` e `dono()`. Tentativas de leitura, alteração (`PATCH`) ou envio de comandos (`/preparar`, `/carregar`, `/despachar`, etc.) sobre lotes de outras empresas sem compartilhamento ativo retornam 404 Not Found ou 403 Forbidden.
  - **Sensores e Fontes (`/api/v1/sensores/{sensor_id}/vincular`):** Validação por `sensor_da_empresa()`. Sensores cadastrados por outras empresas são inacessíveis para leitura ou vinculação.
  - **Ambientes (`/api/v1/ambientes/{ambiente_id}`):** Validação por `ambiente_da_empresa()`. Ambientes de câmaras/compartimentos de terceiros são bloqueados.
  - **Viagens e Rastreio (`/api/v1/viagens/{codigo}`):** Validação por `viagem_acessivel()`. Acesso a rotas e comandos restritos à empresa titular.
  - **Ocorrências e Alertas (`/api/v1/alertas/{alerta_id}/tratar`):** Ocorrências de outras empresas não podem ser tratadas nem visualizadas.
  - **Equipe e Gestão (`/api/v1/equipe/{conta_id}`):** A alteração de vínculos só permite operar sobre participantes da empresa autenticada.
- **Proteção contra Spoofing de Payload:** O backend utiliza validação Pydantic estrita com `extra="forbid"`, rejeitando campos injetados maliciosamente (`empresa_id`, `owner_id`), e valida que operações dependem exclusivamente do contexto do servidor.

---

## 2. Auditoria e Formato dos Logs de Bloqueio

Todas as tentativas de ataque, acessos indevidos a recursos alheios ou falhas de segundo fator geram logs explícitos no formato obrigatório:

```text
[MISSAO:<CODIGO_MISSAO>][BLOQUEIO][<CONTROLE>] motivo=<motivo> | user_id=<user_id> | resource_id=<resource_id>
```

Exemplos reais registrados nos testes:
- `[MISSAO:K7Q2M9][BLOQUEIO][2FA] motivo=segundo_fator_ausente | user_id=2 | resource_id=None`
- `[MISSAO:K7Q2M9][BLOQUEIO][2FA] motivo=codigo_otp_invalido_ou_expirado | user_id=2 | resource_id=None`
- `[MISSAO:K7Q2M9][BLOQUEIO][2FA] motivo=codigo_otp_ja_utilizado | user_id=2 | resource_id=None`
- `[MISSAO:K7Q2M9][BLOQUEIO][AUTH] motivo=tentativa_uso_mfa_token_como_access_token | user_id=None | resource_id=None`
- `[MISSAO:K7Q2M9][BLOQUEIO][2FA] motivo=codigo_recuperacao_ja_utilizado | user_id=2 | resource_id=None`
- `[MISSAO:K7Q2M9][BLOQUEIO][IDOR] motivo=tentativa_acesso_lote_alheio_ou_inexistente | user_id=3 | resource_id=PS-BETA99`
- `[MISSAO:K7Q2M9][BLOQUEIO][IDOR] motivo=tentativa_acesso_sensor_alheio_ou_inexistente | user_id=3 | resource_id=1`
- `[MISSAO:K7Q2M9][BLOQUEIO][IDOR] motivo=tentativa_acesso_empresa_sem_vinculo | user_id=3 | resource_id=3`

---

## 3. Variáveis de Ambiente Necessárias (.env)

No arquivo `.env` (nunca commitado no Git), as variáveis essenciais para os controles são:

```env
# Credenciais do Administrador Inicial da Plataforma
PLANTSYNC_USUARIO=seu_usuario
PLANTSYNC_SENHA=[REMOVIDO]
PLANTSYNC_EMPRESA_INICIAL=Operação existente
PLANTSYNC_CHAVE_DISPOSITIVO=[REMOVIDO]

# Controles de Segurança Obrigatórios
PLANTSYNC_CODIGO_MISSAO=K7Q2M9
PLANTSYNC_TOTP_KEY=[REMOVIDO]
PLANTSYNC_TOTP_WINDOW=1
PLANTSYNC_API_URL=http://localhost:8000
```

> **Atenção:** No repositório, o arquivo `.env.example` contém exclusivamente exemplos sintéticos sem nenhuma chave real ou senha operacional.

---

## 4. Estrutura de Arquivos da Entrega

```text
seguranca/
├── README.md                      # Este documento de referência e execução
├── modelo-ameacas.md              # Análise de ameaças STRIDE, ativos, atores e mitigações
├── uso-de-ia.md                   # Relatório transparente de uso de ferramentas de IA
├── testes/
│   ├── test_2fa_otp.py            # Teste automatizado completo de 2FA (TOTP + Recovery)
│   └── test_idor.py               # Teste automatizado de isolamento e proteção contra IDOR
└── evidencias/
    ├── teste_2fa_K7Q2M9.txt       # Saída e logs da execução do teste de 2FA
    └── teste_idor_K7Q2M9.txt      # Saída e logs da execução do teste de IDOR
```

---

## 5. Como Executar os Testes Automatizados

### Pré-requisitos
Certifique-se de que o ambiente virtual está ativo e as dependências instaladas:

```bash
cd back_end
source .venv/bin/activate
pip install -r requirements.txt
```

### Execução dos Testes com Geração de Evidências

```bash
# Executar Teste de 2FA
python seguranca/testes/test_2fa_otp.py 2>&1 | tee seguranca/evidencias/teste_2fa_K7Q2M9.txt

# Executar Teste de IDOR
python seguranca/testes/test_idor.py 2>&1 | tee seguranca/evidencias/teste_idor_K7Q2M9.txt
```

Os scripts testam cenários legítimos e de contorno (antes e depois da ativação dos controles), validando os códigos de status HTTP e gravando os logs de bloqueio contendo o código de missão.
