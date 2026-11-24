# Modelo de Ameaças: PlantSync (masterv2)

Este documento apresenta a modelagem de ameaças para o sistema **PlantSync**, com foco nos controles de segurança implementados: **Autenticação de Dois Fatores (2FA)** e **Proteção contra Insecure Direct Object References (IDOR)** na arquitetura multiempresa da branch `masterv2`.

---

## 1. Visão Geral da Arquitetura e Escopo

O PlantSync é uma plataforma de monitoramento e rastreabilidade logística da cadeia do frio de frutas no Vale do São Francisco.
- **Backend:** FastAPI (Python 3.14), SQLAlchemy ORM, banco de dados SQLite/PostgreSQL.
- **Arquitetura de Acesso:** Multiempresa (Multi-tenant), onde diferentes produtores, cooperativas e transportadoras compartilham o mesmo banco de dados, exigindo segregação lógica estrita.
- **Autenticação:** Baseada em sessões com tokens opacos (`pss_...` com hash SHA-256 no banco), suporte a MFA (`psm_...`) e cabeçalho `X-Empresa-ID` para seleção contextual da empresa ativa.

---

## 2. Ativos a Proteger

1. **Credenciais e Segredos Criptográficos:**
   - Senhas dos usuários (hashes com sal).
   - Segredos TOTP (chaves Base32 de 2FA).
   - Códigos de recuperação de uso único.
   - Chave de criptografia mestre (`PLANTSYNC_TOTP_KEY`).
2. **Dados Operacionais e Comerciais (Multiempresa):**
   - Dados de lotes de frutas (variedade, peso, cliente, destino, laudos de qualidade).
   - Leituras contínuas de temperatura, umidade e luminosidade (ThingSpeak e leituras manuais).
   - Histórico e rotas de viagens refrigeradas, posições de GPS e paradas.
3. **Integridade das Operações e Alertas:**
   - Transições de estado dos lotes (preparar, carregar, despachar, receber, retornar).
   - Tratamento e reconhecimento de ocorrências de quebra da cadeia do frio.
   - Gestão de membros da equipe e concessão de permissões.

---

## 3. Atores de Ameaça

| Ator | Descrição | Motivação | Nível de Acesso Inicial |
| :--- | :--- | :--- | :--- |
| **Atacante Externo** | Indivíduo não autenticado na Internet | Obter acesso a contas, roubo de dados de clientes, espionagem industrial | Nenhum (apenas endpoints públicos) |
| **Usuário Malicioso Interno (IDOR Horizontal)** | Usuário legítimo da Empresa A | Acessar ou sabotar cargas, lotes, sensores ou laudos da concorrente Empresa B | Autenticado na Empresa A |
| **Usuário com Privilégio Limitado (Vertical)** | Usuário com papel `cliente` ou operador | Elevar privilégios para `administrador` ou alterar configurações da organização | Autenticado com papel restrito |
| **Intermediário na Rede (MitM)** | Atacante com capacidade de interceptação de tráfego | Capturar tokens de autenticação ou reutilizar tokens OTP (replay) | Capacidade de inspecionar/injetar requisições |

---

## 4. Superfícies de Ataque

1. **Autenticação e Sessão (`/api/v1/login`, `/api/v1/2fa/...`):**
   - Tentativas de força bruta de senha e de código TOTP de 6 dígitos.
   - Replay de códigos OTP já utilizados dentro da mesma janela temporal.
   - Reuso de códigos de recuperação (recovery codes) descartáveis.
   - Tentativa de usar o token temporário `mfa_token` diretamente em rotas restritas.
2. **Recursos Operacionais com Identificadores na URL (`/api/v1/...`):**
   - `/api/v1/lotes/{codigo}` (leitura, edição, comandos de fluxo).
   - `/api/v1/sensores/{sensor_id}/vincular` e `/desvincular`.
   - `/api/v1/ambientes/{ambiente_id}`.
   - `/api/v1/viagens/{codigo}` e sub-rotas de rastreio/posições.
   - `/api/v1/alertas/{alerta_id}/tratar`.
   - `/api/v1/equipe/{conta_id}` (alteração de papel/vínculo de membros).
3. **Manipulação de Parâmetros de Payload:**
   - Injeção de `empresa_id` ou `owner_id` em corpos de requisição para associar recursos a outras empresas.

---

## 5. Análise de Ameaças STRIDE e Mitigações

### 5.1. Spoofing (Falsificação de Identidade)
- **Ameaça:** Atacante descobre ou adivinha a senha de um operador e realiza login sem autorização.
- **Mitigação Aplicada:**
  - Implantação de **Autenticação de Dois Fatores (2FA)** obrigatória com algoritmo TOTP (RFC 6238).
  - A posse exclusiva da senha não concede acesso: o servidor emite um `mfa_token` temporário (5 minutos de vida) e exige um token OTP de 6 dígitos gerado por aplicativo autenticador.
  - Bloqueio imediato com 401 caso o OTP esteja ausente ou incorreto, com registro do código de missão no log de auditoria.

### 5.2. Tampering (Adulteração de Dados)
- **Ameaça:** Injeção de parâmetros de identificação no JSON da requisição (ex.: `"empresa_id": 2`) para modificar o dono de um lote ou associar um sensor alheio à sua própria câmara fria.
- **Mitigação Aplicada:**
  - Modelos Pydantic configurados com `extra="forbid"`, gerando erro de validação (HTTP 400/422) caso campos não autorizados sejam enviados.
  - A autorização ignora qualquer campo de identidade do payload; o contexto de segurança é extraído unicamente da sessão autenticada no servidor (`acessos.obter_contexto`).

### 5.3. Repudiation (Não-repúdio)
- **Ameaça:** Operador da Empresa A move um lote para outra etapa ou trata um alerta crítico e depois nega a autoria da ação.
- **Mitigação Aplicada:**
  - O sistema grava eventos de auditoria nas tabelas `operacao_eventos` e `eventos_acesso`, contendo `autor_id`, `empresa_id`, data/hora UTC e detalhes da transação.
  - Toda tentativa de ataque IDOR ou falha de 2FA emite logs explícitos com identificadores de usuário, recurso e o código da missão (`PLANTSYNC_CODIGO_MISSAO`).

### 5.4. Information Disclosure (Vazamento de Informações / IDOR)
- **Ameaça:** Usuário autenticado na Empresa A itera códigos de lotes (`PS-BETA01`, `PS-BETA02`) ou IDs de sensores via `GET` para espionar a operação de empresas concorrentes.
- **Mitigação Aplicada:**
  - Controle de acesso baseado em posse em nível de serviço (`lote_acessivel`, `sensor_da_empresa`, `viagem_acessivel`, `ambiente_da_empresa`).
  - O servidor verifica se o recurso pertence à `empresa_id` extraída da sessão autenticada (ou possui compartilhamento explícito e ativo).
  - Se o recurso pertencer a terceiros, retorna **404 Not Found** (ocultando a existência do recurso) ou **403 Forbidden**, e grava log de bloqueio com `[MISSAO:...][BLOQUEIO][IDOR]`.

### 5.5. Denial of Service (Negação de Serviço)
- **Ameaça:** Replay de códigos OTP capturados em trânsito para estabelecer sessões concorrentes; esgotamento de tentativas.
- **Mitigação Aplicada:**
  - **Mecanismo Anti-Replay:** O servidor armazena o último intervalo de tempo (`totp_last_timestep`) e bloqueia a reutilização do mesmo código OTP dentro do ciclo de 30 segundos.
  - **Uso Único de Recovery Codes:** Cada código de recuperação é invalidado imediatamente após o primeiro uso gravando o timestamp UTC em `codigos_recuperacao_conta.usado_em`.

### 5.6. Elevation of Privilege (Elevação de Privilégio)
- **Ameaça:** Membro de uma empresa altera seu cabeçalho `X-Empresa-ID` para o ID de uma empresa parceira ou administradora para assumir privilégios indevidos; tentativa de alterar administradores de outra empresa via `PATCH /api/v1/equipe/{conta_id}`.
- **Mitigação Aplicada:**
  - A função `obter_contexto()` valida se a conta do usuário possui vínculo ativo na tabela `vinculos_conta` com a empresa indicada no cabeçalho. Caso contrário, responde **403 Forbidden** e loga tentativa de IDOR.
  - A rota `PATCH /api/v1/equipe/{conta_id}` valida obrigatoriamente se o `conta_id` é membro da empresa autenticada.

---

## 6. Riscos Residuais e Recomendações Futuras

1. **Armazenamento de Chaves Criptográficas:**
   - *Risco Residual:* A chave `PLANTSYNC_TOTP_KEY` reside em variável de ambiente. Em caso de comprometimento total do servidor host, a chave poderia ser lida.
   - *Recomendação:* Em ambientes de produção corporativos, integrar a um serviço de gerenciamento de chaves (KMS / HashiCorp Vault) ou módulo HSM.
2. **Rate Limiting Granular para OTP:**
   - *Risco Residual:* Embora o tempo de vida do `mfa_token` seja curto (5 minutos) e o espaço de busca seja de 1.000.000 de códigos, um atacante com altíssima taxa de requisições poderia tentar força bruta antes da expiração.
   - *Recomendação:* Adicionar limitação de 5 tentativas consecutivas de OTP por sessão MFA, invalidando o `mfa_token` após exceder o limite.
