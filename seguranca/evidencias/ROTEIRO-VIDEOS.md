# Roteiro dos vídeos — missão CP5TN0

Dois vídeos de **até 90 segundos**, um por controle, mostrando o ANTES e o DEPOIS.

| Controle | Arquivo do vídeo |
|---|---|
| 2FA (TOTP) | `video_2fa_CP5TN0.mp4` |
| IDOR (isolamento multiempresa) | `video_idor_CP5TN0.mp4` |

Salve os dois em `seguranca/evidencias/` com exatamente esses nomes. O GitHub recusa arquivos acima de 100 MB e avisa a partir de 50 MB. Grave em 720p, ou comprima antes de versionar. Se ainda ficar grande, publique o vídeo fora do repositório e coloque o link no [README](../README.md).

## Antes de gravar (fora da câmera)

1. Use só o banco de teste e dados sintéticos. As contas `operador_alpha_idor`, `operador_beta_idor` e `operador_2fa_teste` são criadas pelos scripts.
2. Faça todos os `export` (principalmente `PLANTSYNC_TOTP_KEY`) **antes** de começar a gravar e limpe o terminal (`clear`). A chave, tokens `Bearer`, o `mfa_token` e a URI `otpauth://` completa **não podem aparecer** no vídeo.
3. Aumente a fonte do terminal (16 pt ou mais) e feche abas, notificações e janelas com dados pessoais.
4. Deixe os comandos prontos no histórico do terminal (seta para cima), para não digitar durante a gravação.
5. Gravação de tela: OBS Studio ou, no Windows, Xbox Game Bar (`Win + Alt + R`). Narre em voz ou use legendas curtas.
6. O código **CP5TN0** precisa aparecer na tela nos dois vídeos: no cabeçalho da saída dos testes e nos logs `[MISSAO:CP5TN0][BLOQUEIO]`.

Os comandos de API e testes estão na seção **Execução** do [README](../README.md). Use os mesmos valores de `DATABASE_URL`, `PLANTSYNC_API_URL` e `PLANTSYNC_CODIGO_MISSAO=CP5TN0`.

---

## Vídeo 1 — `video_2fa_CP5TN0.mp4`

**Preparação:** API rodando com `PLANTSYNC_CODIGO_MISSAO=CP5TN0` e um banco de teste **novo** (apague `plantsync_teste.db` antes), para a conta de teste começar sem 2FA. Deixe dois painéis visíveis: à esquerda o terminal dos testes, à direita o log da API.

| Tempo | O que mostrar | O que dizer |
|---|---|---|
| 0–10 s | Título "PlantSync · 2FA (TOTP) · Missão CP5TN0" e a seção 2FA do README | "Controle 1: autenticação em dois fatores com TOTP." |
| 10–20 s | Rodar `python seguranca/testes/test_2fa_otp.py` e parar o olhar na linha `[ANTES] Login com senha sem OTP aceito diretamente` | "Antes: com a conta sem 2FA, só a senha já dá acesso. Quem roubar a senha entra." |
| 20–35 s | Linhas `[Setup]` e `[Confirm]`, depois `[DEPOIS] 2FA ativado` | "Ativamos o 2FA: o segredo é cifrado no banco e são gerados códigos de recuperação de uso único." |
| 35–60 s | Linhas `[2a]` a `[4]`: login devolve `mfa_required: True`, sem OTP `401`, OTP errado `401`, OTP válido `200` | "Depois: a senha sozinha não basta. Sem OTP ou com OTP errado o acesso é negado. Com o OTP correto, entra." |
| 60–75 s | Linhas `[5]` a `[7b]`: replay `401`, `mfa_token` como token `401`, recuperação 1º uso `200` e 2º uso `401` | "Tentativas de contorno também falham: reusar o OTP, usar o token temporário como sessão e reusar um código de recuperação." |
| 75–90 s | Painel do log da API com `[MISSAO:CP5TN0][BLOQUEIO][2FA]` e a linha final `TODOS OS TESTES DE 2FA PASSARAM` | "Cada bloqueio fica registrado com o código da missão, CP5TN0." |

**Opcional, se sobrar tempo:** em vez das linhas `[2a]`–`[4]`, mostrar no frontend o login pedindo o código do app autenticador. Não mostre o QR code nem os códigos de recuperação de forma legível.

---

## Vídeo 2 — `video_idor_CP5TN0.mp4`

**Preparação:** o ANTES exige a checagem de posse desativada. Para não arriscar commitar código vulnerável e evitar reiniciar a API durante a gravação, rode **duas APIs ao mesmo tempo**, cada uma com seu banco:

1. Crie uma cópia de trabalho separada só para o ANTES: `git worktree add ../PlantSync-antes main`.
2. Em `../PlantSync-antes`, aplique o patch temporário descrito em **README → Execução → ANTES do IDOR** e suba a API na **porta 8001**, com `DATABASE_URL` apontando para `plantsync_teste_antes.db`.
3. No repositório principal (sem alteração), suba a API normal na **porta 8000**, com `DATABASE_URL` apontando para `plantsync_teste.db`.
4. No terminal dos testes, antes de cada comando, ajuste `PLANTSYNC_API_URL` e `DATABASE_URL` para a API correspondente. O teste precisa usar o mesmo banco da API que está atacando.
5. **Depois da gravação:** `git worktree remove --force ../PlantSync-antes` e confirme com `git status` e `git diff` que o repositório principal continua limpo.

| Tempo | O que mostrar | O que dizer |
|---|---|---|
| 0–10 s | Título "PlantSync · IDOR · Missão CP5TN0" e a seção IDOR do README | "Controle 2: isolamento entre empresas contra IDOR." |
| 10–20 s | Em `../PlantSync-antes`: `git diff --stat`, mostrando que o patch é local e não commitado | "Para mostrar o antes, desligamos a checagem de posse só nesta cópia local, na porta 8001." |
| 20–45 s | `python seguranca/testes/test_idor_antes.py` contra a 8001, com destaque para as linhas `ACEITO (vulnerável)` e `RESULTADO ANTES: 5 de 6` | "Antes: o usuário da Empresa A lê, altera e envia comando ao lote da Empresa B, vincula o sensor dela e forja o cabeçalho X-Empresa-ID. Cinco de seis ataques passam, sem nenhum registro." |
| 45–70 s | `python seguranca/testes/test_idor.py` contra a 8000 (código original), com `404`/`403` em [1]–[6] e `200` em [7]–[9] | "Depois, com o controle ativo: os mesmos seis ataques são bloqueados e os donos continuam operando normalmente." |
| 70–85 s | Log da API 8000 com `[MISSAO:CP5TN0][BLOQUEIO][IDOR] motivo=tentativa_acesso_lote_alheio...`, `sensor_alheio...` e `empresa_sem_vinculo` | "Cada tentativa bloqueada fica registrada com o código da missão." |
| 85–90 s | Linha final `TODOS OS TESTES DE IDOR PASSARAM` | "Mesmos cenários, antes e depois. Evidências em seguranca/evidencias." |

---

## Checklist final

- [ ] Cada vídeo tem no máximo 90 s.
- [ ] O código **CP5TN0** aparece na tela nos dois vídeos.
- [ ] Os nomes são `video_2fa_CP5TN0.mp4` e `video_idor_CP5TN0.mp4`.
- [ ] Nenhuma chave, token, `mfa_token`, URI `otpauth://` completa, QR code ou dado pessoal aparece.
- [ ] O worktree do ANTES foi removido e `git diff` no repositório principal está vazio.
- [ ] Os arquivos ficaram abaixo de 100 MB, ou o link foi colocado no README.
