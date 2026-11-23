# API da operação por empresa

Prefixo `/api/v1`. A documentação interativa fica em `/docs` e o esquema em `/openapi.json` no servidor configurado. O frontend usa o mesmo contrato das integrações para as regras do domínio.

O desenho de dados, as chaves e as fronteiras de autorização estão em [Modelo operacional](MODELO-OPERACIONAL.md).

## Autenticação e contexto

`POST /api/v1/login` recebe usuário ou e-mail e senha. A resposta contém token de sessão, validade, usuário e organizações permitidas. Envie a sessão no cabeçalho `Authorization: Bearer <TOKEN>` e escolha a organização com `X-Empresa-ID: <ID>`. A escolha é validada pelo vínculo no servidor. Uma conta com uma única organização pode usar esse contexto como padrão.

```json
{"usuario": "operador@example.com", "senha": "VALOR_LOCAL"}
```

`GET /contexto` informa conta, empresa, papel e permissões atuais. `POST /logout` revoga a sessão. `POST /conta/senha` recebe `senha_atual` e `nova_senha` e revoga as sessões afetadas após a troca.

Integrações usam credencial própria, também no cabeçalho Bearer. Sessão, credencial de integração, convite e código público são capacidades distintas. O segredo da integração aparece uma vez na criação e deve ficar no sistema que fará as chamadas.

Configure a coleta com retenção do logger `plantsync.auditoria` na implantação. Respostas `403` e `404` a uma credencial de integração reconhecida registram o ID da credencial, a empresa emissora, o método, o modelo da rota e o código HTTP. A configuração do coletor deve incluir horário e controlar acesso e volume. Os eventos omitem parâmetros da rota, cabeçalhos e corpo.

## Gestão

| Recurso | Operações |
|---|---|
| Empresas da plataforma | `GET /empresas`, `POST /empresas`, `PATCH /empresas/{empresa_id}` |
| Primeiro administrador | `POST /empresas/{empresa_id}/convites` |
| Equipe da organização | `GET /equipe`, `PATCH /equipe/{conta_id}` |
| Convites | `GET /equipe/convites`, `POST /equipe/convites`, `DELETE /equipe/convites/{convite_id}` |
| Aceite | `POST /convites/aceitar` com token e identidade do destinatário |
| Papéis | `GET /papeis`, `PATCH /papeis/{papel}` |
| Integrações | `GET /integracoes`, `POST /integracoes`, `DELETE /integracoes/{integracao_id}` |
| Preferências próprias | `GET /perfil`, `PATCH /perfil` |
| Identidade da organização | `GET /configuracoes/empresa`, `PATCH /configuracoes/empresa` |
| Fluxo versionado | `GET /configuracoes/fluxo`, `PATCH /configuracoes/fluxo` |

As operações de administração verificam o papel e o vínculo atual. A administração da plataforma provisiona organizações e seus primeiros administradores. O acesso aos lotes depende dos direitos operacionais concedidos.

## Preparação e sensores

| Recurso | Operações |
|---|---|
| Frutas e faixas da empresa | `GET /frutas`, `POST /frutas`, `PATCH /frutas/{fruta_id}` |
| Ambientes | `GET /ambientes`, `POST /ambientes` |
| Fontes de medição | `GET /sensores`, `POST /sensores` |
| Instalação de sensor | `POST /sensores/{sensor_id}/vincular`, `POST /sensores/{sensor_id}/desvincular` |
| Sincronização com ThingSpeak | `POST /sincronizar` |
| Medição de uma fonte manual | `POST /sensores/{sensor_id}/leituras` |

Exemplo de ambiente

```json
{"name": "Câmara fria 01", "type": "camara"}
```

O catálogo recebe `nome`, `temp_min_c`, `temp_max_c`, `umidade_min_pct`, `umidade_max_pct`, `fonte` e, opcionalmente, `risco_no_frio`. A edição exige `version` da consulta. Alterar uma faixa preserva a faixa já registrada nos lotes existentes. O catálogo personalizado pertence à empresa selecionada.

Exemplo de sensor conectado ao ambiente

```json
{"name": "Sensor da câmara", "type": "thingspeak", "channel": 1234567, "environmentId": 1}
```

Medições preservam a origem e o horário medido. A identificação de entrada pertence à fonte correspondente. A importação pode ser repetida e admite dados atrasados. Leituras são associadas aos lotes pelos intervalos de permanência e instalação, respeitando os direitos da empresa.

## Lotes e fases

| Recurso | Operações |
|---|---|
| Lotes | `GET /lotes`, `POST /lotes`, `GET /lotes/{codigo}`, `PATCH /lotes/{codigo}` |
| Preparação | `POST /lotes/{codigo}/preparar` |
| Carregamento | `POST /lotes/{codigo}/carregar` |
| Despacho | `POST /lotes/{codigo}/despachar` |
| Recebimento | `POST /lotes/{codigo}/receber` |
| Retorno | `POST /lotes/{codigo}/retornar` |
| Regularização | `POST /lotes/{codigo}/validar-despacho` |
| Aceite de responsabilidade | `POST /lotes/{codigo}/confirmar-transferencia` |
| Medições | `GET /lotes/{codigo}/leituras` |
| Histórico | `GET /lotes/{codigo}/historico` |

Exemplo de criação com início da preparação

```json
{
  "fruitId": "uva",
  "client": "Cliente da operação",
  "destination": "Recife",
  "environmentId": 1,
  "boxes": 100,
  "weightKg": 500
}
```

O código pode ser informado no padrão aceito pelo esquema ou gerado pelo servidor. A resposta fornece `id`, `version`, fase, faixa e ações permitidas. As fases operacionais são `0` preparação, `1` aguardando despacho, `2` em trânsito e `3` recebido. Carregamento, despacho e demais mudanças geram eventos próprios.

Nas alterações, envie a versão obtida na consulta. Um conflito devolve `409`, permitindo atualizar e revisar antes de repetir. Horários informados devem ter fuso, por exemplo `2026-11-23T17:32:00Z`. Retornos e validações exigem justificativa em `reason`.

```json
{
  "version": 1,
  "environmentId": 2,
  "tripId": "V-1",
  "effectiveAt": "2026-11-23T17:32:00Z",
  "reason": "Carregamento conferido pela expedição."
}
```

## Repetição de comandos

Integrações devem enviar `Idempotency-Key` nas mutações operacionais. Use uma chave estável para o mesmo comando durante retries. Reutilizar a chave para outro conteúdo gera conflito. Mudança relevante de permissões ou de concessão também impede reproduzir uma resposta gravada sob direitos anteriores.

Fase, associação, responsabilidade e evento são persistidos de forma transacional. A resposta do despacho em grupo informa os lotes movimentados e os motivos dos itens não elegíveis.

## Compartilhamento

`POST /lotes/{codigo}/compartilhamentos` cria uma concessão para uma organização, com direitos e intervalo de dados. `POST /compartilhamentos/{comp_id}/aceitar` confirma a participação. O aceite identifica a empresa destinatária. Convite pendente não concede acesso.

`GET /compartilhamentos` lista convites e concessões do destinatário. O titular consulta e revoga pelo recurso do lote. O cliente recebe apenas seus lotes, dados e trechos permitidos. Uma viagem compartilhada não concede acesso aos outros lotes.

## Viagens e localização

| Recurso | Operações |
|---|---|
| Viagens | `GET /viagens`, `POST /viagens`, `GET /viagens/{codigo}` |
| Despacho em conjunto | `POST /viagens/{codigo}/despachar` |
| Fonte ativa | `POST /viagens/{codigo}/rastreio/iniciar`, `POST /viagens/{codigo}/rastreio/encerrar` |
| Posições | `GET /viagens/{codigo}/posicoes`, `POST /viagens/{codigo}/posicoes` |

Cada viagem mantém paradas e lotes. A fonte é escolhida explicitamente. Mudanças de fonte encerram e abrem períodos registrados. Use `source` igual a `celular` ou `externa` conforme o fluxo.

Exemplo de posição

```json
{
  "entryId": "posicao-001",
  "source": "externa",
  "latitude": -9.3891,
  "longitude": -40.5031,
  "accuracy": 12,
  "measuredAt": "2026-11-23T18:10:00Z"
}
```

A posição registra medição e recebimento separadamente. Dados repetidos mantêm uma identidade por fonte. A consulta respeita o trecho autorizado e o recebimento dos lotes, com quebra de percurso quando houver troca de fonte ou lacuna identificada.

## Conservação, alertas e documentos

`GET /alertas` lista ocorrências acessíveis. `POST /alertas/{alerta_id}/tratar` registra o tratamento e a versão esperada. O fluxo define o limite de ausência de medições quando a organização optar por ativar essa regra.

`GET /lotes/{codigo}/laudo` consulta o laudo autenticado. `POST /lotes/{codigo}/laudo` emite acesso por segredo e `DELETE` revoga os links emitidos para o lote. `GET /laudos/{token}` abre o link válido. Cada emissão e revisão identifica seu contexto no histórico.

`GET /lotes/{codigo}/laudo/revisoes` lista as emissões e `GET /lotes/{codigo}/laudo/revisoes/{revisao_id}` consulta o retrato emitido. O retrato inclui até 1.000 leituras e 500 eventos, com contagens totais; use as consultas paginadas autenticadas para obter o restante. Desative o registro das URLs de acesso no servidor e no proxy, pois o caminho do laudo contém seu segredo: no Uvicorn, use `--no-access-log`.

`GET /publico/{codigo}` fornece o resumo público. O QR usa esse código como vínculo e não concede ações operacionais. O selo continua em avaliação até que os critérios de conservação e cobertura sejam aprovados.

## Respostas e erros

Consultas paginadas com metadados retornam `items`, `total`, `offset` e `limit`. Listas simples usam arrays conforme o esquema interativo. Leituras incluem `analysis` e a indicação de quebra da série quando aplicável.

Erros da aplicação usam o campo `erro`. Sessão ausente ou inválida responde `401`, acesso insuficiente `403`, recurso indisponível `404`, conflito `409` e limite de login `429` com `Retry-After`. A validação de campos é apresentada pelo handler da aplicação. Consulte o esquema para limites e campos de cada operação.

Após a conversão, as rotas internas sem `/v1` respondem `410`. Os acessos públicos antigos e a consulta restrita do dispositivo são tratados pela compatibilidade prevista na migração.
