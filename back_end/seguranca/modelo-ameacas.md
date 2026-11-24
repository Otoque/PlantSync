# Modelo de ameaças — PlantSync

**Escopo:** API FastAPI multiempresa, banco SQLAlchemy e frontend JavaScript. Usuários acessam a API v1 por sessão; dispositivos IoT usam rotas legadas com chave própria. O isolamento por empresa é aplicado às rotas operacionais da API v1.

| Ativo / ameaça (STRIDE) | Cenário | Controle atual | Estado / risco residual |
|---|---|---|---|
| Conta de usuário — **Spoofing** | Senha roubada usada para entrar | TOTP opcional, códigos de recuperação descartáveis e token MFA temporário quando 2FA está ativo | Parcial: contas sem 2FA ainda entram apenas com senha; não há imposição global nem limite de tentativas documentado. |
| Segredo TOTP — **Information Disclosure** | Leitura do banco expõe a semente do autenticador | Segredo cifrado com Fernet; códigos de recuperação guardados como hashes | Depende de proteger `PLANTSYNC_TOTP_KEY` fora do banco e de rotacioná-la se exposta. |
| Dados de outra empresa — **Information Disclosure / Tampering** | Usuário troca ID de lote, sensor ou empresa na requisição | API v1 deriva identidade da sessão e verifica vínculo/posse; testes exercitam leitura, alteração e comandos cruzados | Parcial: revisar rotas novas e legadas. As rotas IoT autenticam por chave de dispositivo, não pela sessão multiempresa do usuário. |
| Sessão e operações — **Repudiation** | Usuário nega ação ou tentativa de acesso indevido | Eventos de operação e logs de bloqueio disponíveis no backend | Retenção, integridade e correlação dos logs precisam de validação operacional. |

**Testes previstos:** `testes/test_2fa_otp.py` verifica OTP ausente/inválido, replay e recuperação de uso único; `testes/test_idor.py` usa duas empresas para verificar negação cruzada e acesso do titular. Registre resultados reais e associe o código de missão oficial nas evidências. A equipe ainda deve gravar demonstração no dispositivo físico e documentar eventuais limitações.
