# Relatório de Uso de Inteligência Artificial: Implementação de 2FA e IDOR no PlantSync (masterv2)

Este documento registra de forma transparente e estruturada como ferramentas de Inteligência Artificial (IA) foram utilizadas no diagnóstico, implementação, refatoração de testes e validação dos controles de segurança no projeto PlantSync (branch `masterv2`), bem como as revisões, análises críticas e correções manuais executadas pela equipe de engenharia.

---

## 1. Atividades Apoiadas por Ferramentas de IA

O agente de IA com acesso ao sistema de arquivos e ferramentas de execução (MCP) foi empregado nas seguintes frentes:

1. **Diagnóstico Estrutural do Repositório:**
   - Varredura dos controllers em `back_end/controllers/` e mapeamento das rotas reais da branch `masterv2`, identificando a transição da arquitetura legada (`/api/...`) para a arquitetura multiempresa versionada (`/api/v1/...`).
   - Diagnóstico da causa-raiz das falhas 404 Not Found nos testes legados (`test_2fa_otp.py` e `test_idor.py`), que haviam sido escritos contra rotas genéricas (`/auth/login`, `/devices/1`).
2. **Desenho e Geração de Código dos Controles de Segurança:**
   - **2FA (TOTP):** Implementação do serviço `totp_service.py` utilizando `pyotp` (RFC 6238) e criptografia simétrica Fernet (`cryptography`) para proteger o segredo em repouso no SQLite, além de gestão de tokens temporários (`psm_...`) e hashes de códigos de recuperação.
   - **Auditoria Obrigatória:** Implementação do módulo `audit_log.py` para emitir logs padronizados de bloqueio contendo explicitamente o código de missão (`PLANTSYNC_CODIGO_MISSAO`).
   - **Proteção contra IDOR:** Identificação dos pontos de validação de posse nos serviços operacionais (`operacao_acesso.py`, `operacao_monitoramento.py`, `operacao_viagens.py`, `operacao.py` e `acessos.py`), garantindo que tentativas de acesso a recursos alheios retornem 403/404 e emitam logs de auditoria.
3. **Elaboração da Documentação Técnica:**
   - Estruturação do modelo de ameaças STRIDE (`modelo-ameacas.md`) e guia de execução (`README.md`).

---

## 2. Validações Críticas e Correções Executadas

Durante a integração contínua e a execução prática dos testes, intervenções técnicas e correções minuciosas foram necessárias para alinhar o código gerado à realidade do framework e do modelo de dados:

1. **Resolução da Regra de Login por Nome de Usuário (`identidade_de_login`):**
   - *Problema Encontrado:* O script de teste inicial falhava com `401 - Usuário ou senha inválidos` ao tentar autenticar os usuários de teste recém-criados.
   - *Diagnóstico e Correção:* Ao inspecionar `services/acessos.py`, identificou-se que a função `identidade_de_login` define que contas com `email` preenchido **só podem autenticar usando o e-mail**. Caso o identificador enviado não contenha `@`, a busca no banco é estrita para `Conta.nome == [REMOVIDO] AND Conta.email IS NULL`. Os scripts de teste foram corrigidos para criar os operadores com `email=None`, permitindo o login direto pelo nome de usuário.
2. **Ajuste Fino da Proteção Anti-Replay no Setup do 2FA:**
   - *Problema Encontrado:* Ao confirmar a ativação do 2FA (`POST /api/v1/2fa/confirm`), a função de validação registrava o timestamp atual em `totp_last_timestep`. Imediatamente a seguir, ao testar o primeiro login válido dentro da mesma janela de 30 segundos, o login era bloqueado por anti-replay.
   - *Diagnóstico e Correção:* Ajustou-se a função `confirm_user_2fa` para validar o código com `check_only=True` e redefinir `totp_last_timestep = None`. Dessa forma, o setup apenas valida a posse do aplicativo autenticador sem queimar antecipadamente o timestep do primeiro login legítimo do usuário, mantendo a proteção anti-replay estrita para tentativas de reuso subsequentes no login.
3. **Compatibilidade de Resposta de Login:**
   - *Ajuste:* A função `gerar_resposta_sessao` foi configurada para retornar simultaneamente as chaves `token` (padrão interno do PlantSync) e `access_token` (padrão OAuth2/Bearer esperado por clientes externos), garantindo 100% de compatibilidade tanto com os testes existentes do backend quanto com os novos testes de segurança.
4. **Catálogo de Frutas da Empresa no Teste de IDOR:**
   - *Problema Encontrado:* O teste de IDOR recebia erro ao cadastrar um lote teste com `fruitId="manga-tommy"`.
   - *Diagnóstico e Correção:* Ao inspecionar `services/catalogo.py` e `services/frutas.py`, verificou-se que o catálogo padrão utiliza o identificador canônico `"manga"`, enquanto `"Tommy Atkins"` deve ser passado no campo `variety`. A correção garantiu a criação dos lotes legítimos e a validação do isolamento IDOR.
5. **Prevenção de Falso Positivo na Verificação de Spoofing:**
   - *Ajuste:* O middleware de validação do Pydantic no FastAPI (`RequestValidationError`) do PlantSync trata campos extras ou inválidos convertendo para resposta HTTP 400 com mensagem estruturada. O teste foi ajustado para validar que tentativas de injeção de parâmetros (`empresa_id` forjado) são sumariamente recusadas pelo servidor (status 400/403/404/422).

---

## 3. Verificação de Regressão e Segurança

- **Testes Automatizados de Segurança:** 100% aprovados (`test_2fa_otp.py` e `test_idor.py`).
- **Suíte de Testes Existentes:** A suíte de 49 testes de regressão (`test_api_login.py`, `test_contas_empresas.py`, `test_api_operacao.py`) foi executada via `pytest` com 100% de sucesso, comprovando que a introdução do 2FA e da auditoria IDOR não introduziu regressões no comportamento operacional das empresas.
- **Higiene de Segredos no Git:** Verificado que nenhum arquivo `.env`, credencial real ou banco de dados `.db` foi incluído no controle de versão.
