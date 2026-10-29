# Contrato da API do PlantSync

Versão 0.4 (rascunho, 29/10/2026). Este documento descreve o que o backend entrega ao
painel web. Qualquer mudança aqui precisa ser combinada com a frente do frontend.

## Mudanças da v0.4 (em relação à v0.3)

1. **Risco nos dois lados da faixa.** Os graus-hora agora são calculados acima do teto
   **e** abaixo do piso da faixa do lote. O campo `graus_hora` deixou de existir e deu
   lugar a `graus_hora_acima` e `graus_hora_abaixo` (no `risco` da lista e na
   `analise` do detalhe). A `analise` ganhou `nivel_acima`, `nivel_abaixo` e
   `trechos_fora_faixa`. O `nivel` passa a ser o pior dos dois lados.
2. **Fruta com `risco_no_frio`** (opcional): nome do dano que o frio causa na fruta,
   usado no texto do alerta (manga: "corte negro").
3. **Alerta de frio.** `risco_termico` pode vir duas vezes por lote, uma por lado, com o
   novo campo `lado` (`acima` ou `abaixo`).
4. **Lote com `produtor`** (obrigatório no cadastro), `codigo_publico` e `token_laudo`.
5. **Laudo por QR Code:** rotas novas `GET /api/publico/{codigo}` (visão do consumidor)
   e `GET /api/laudos/{token}` (laudo completo do produtor e do importador).

Quem já tem um `back_end/plantsync.db` da v0.3 precisa apagá-lo: as tabelas mudaram e o
banco é recriado na próxima execução.

## Convenções

- Endereço local: `http://localhost:8000`. Todas as rotas começam com `/api`.
- Corpo das requisições e respostas em JSON, codificação UTF-8.
- CORS liberado para o painel em desenvolvimento: `http://localhost:5500` e
  `http://127.0.0.1:5500`. Outras origens entram pela variável `CORS_ORIGENS`
  (lista separada por vírgula).
- Datas e horas dos campos JSON em ISO 8601, sempre em UTC com o sufixo `Z`
  (ex.: `2026-10-25T17:30:00Z`). Quem converte para `America/Recife` (UTC−3) é o
  painel. A única exceção é o texto livre do campo `mensagem` dos alertas, que já vem
  escrito no horário de Recife para ser lido por gente.
- Temperatura em °C, umidade relativa em %, luminosidade em lux.
- Campo sem valor vem como `null` (ex.: luminosidade quando o sensor não mandou).
- Erros têm sempre o mesmo formato, com o código HTTP correspondente:

```json
{ "erro": "Lote 99 não encontrado." }
```

| Código | Quando acontece |
|---|---|
| 200 | Consulta ou ação concluída. |
| 201 | Lote criado. |
| 400 | Dado inválido no corpo da requisição. A mensagem começa pelo campo, ex.: `"fruta: campo obrigatório"`. |
| 404 | Lote, fruta, código, token ou rota inexistente. |
| 502 | O ThingSpeak não respondeu ou respondeu com erro. |

## Conceitos

- **Lote**: uma carga de fruta que sai de uma origem (packing house) para um porto. Tem
  início e, quando chega, fim.
- **Leitura**: uma amostra enviada pelo sensor ao ThingSpeak (a cada 20 s). O backend
  copia as leituras para o banco local.
- **Associação leitura → lote**: uma leitura pertence ao lote quando o horário dela está
  entre o `inicio` e o `fim` do lote. Lote sem `fim` (ainda em trânsito) recebe tudo
  que chegar depois do `inicio`.
- **Faixa segura**: limites de temperatura e umidade de uma fruta, com a fonte. Fica
  cadastrada no banco e pode ser editada pela API; não há valor fixo no código.
- **Cópia da faixa no lote**: ao criar um lote, a faixa da fruta é copiada para ele.
  Editar a fruta depois só vale para os lotes novos; os lotes já cadastrados continuam
  sendo analisados com a faixa que tinham, e o histórico não muda.
- **Graus-hora (°C·h)**: soma, ao longo da viagem, de quanto a temperatura passou do
  limite, multiplicado pelo tempo em que ficou assim. São duas contas separadas:
  - `graus_hora_acima`: calor acima do teto (`temp_max_c`). Ex.: 2 °C acima do teto
    durante 3 h somam 6 °C·h.
  - `graus_hora_abaixo`: frio abaixo do piso (`temp_min_c`). Ex.: manga (piso 10 °C) a
    8,5 °C durante 72 h soma 1,5 × 72 = 108 °C·h.

  Leitura exatamente no piso ou no teto soma 0. Os dois lados importam: na manga, o frio
  abaixo do piso causa corte negro, que pode levar à rejeição da carga (MOVIMENTO
  ECONÔMICO, 2026; PAULL; CHEN, 2016).
- **Nível de risco**: cada lado é classificado em quatro níveis pelos limiares abaixo
  (`nivel_acima` e `nivel_abaixo`). O nível do lote (`nivel`) é **o pior dos dois**,
  porque calor e frio causam danos diferentes e um lado não compensa o outro. Limiares
  do `analytics/eda_plantsync.py`:

| Nível | Graus-hora | Recomendação |
|---|---|---|
| `VERDE` | menos de 5 | Cadeia do frio íntegra ou desvio marginal. Carga liberada. |
| `AMARELO` | de 5 a menos de 20 | Abuso térmico moderado. Priorizar esta carga na expedição. |
| `LARANJA` | de 20 a menos de 50 | Abuso relevante. Inspeção física obrigatória antes do embarque. |
| `VERMELHO` | 50 ou mais | Abuso severo. Redirecionar para mercado interno ou processamento. |

> Os limiares acima foram definidos pela equipe no pipeline analítico e ainda precisam
> ser validados com um produtor parceiro. Valem igualmente para os dois lados; não há
> limiar específico de corte negro além da própria faixa da fruta.

- **Trecho fora da faixa**: leituras seguidas do mesmo lado da faixa (todas acima do
  teto ou todas abaixo do piso), agrupadas em um intervalo com início e fim.
- **Códigos do laudo**: cada lote recebe, no cadastro, dois textos aleatórios (não
  sequenciais, impossíveis de adivinhar a partir de outro lote):
  - `codigo_publico`: vai no QR Code impresso na caixa. Abre só a visão pública.
  - `token_laudo`: segredo entregue ao produtor e ao importador. Abre o laudo completo.

  **Um QR, duas visões.** O QR leva à página do lote com o `codigo_publico`; quem também
  tem o `token_laudo` (link enviado em particular) vê o laudo completo. Usamos um token
  secreto em vez de login porque o login com perfis (RF07) ainda não foi decidido: o
  link funciona como a chave de um documento compartilhado. Por isso o token nunca vai no
  QR, e só o painel interno (`GET /api/lotes/{id}`) o mostra.

## Endpoints

| Método | Rota | Para que serve |
|---|---|---|
| GET | `/api/saude` | Verificar se a API está no ar. |
| GET | `/api/frutas` | Listar as frutas e suas faixas seguras. |
| POST | `/api/frutas` | Cadastrar uma fruta com sua faixa. |
| PUT | `/api/frutas/{id}` | Editar o nome, a faixa ou a fonte de uma fruta. |
| GET | `/api/lotes` | Listar os lotes com o resumo de risco. |
| POST | `/api/lotes` | Cadastrar um lote. |
| GET | `/api/lotes/{id}` | Ver um lote com a análise completa. |
| POST | `/api/lotes/{id}/encerrar` | Marcar a chegada do lote ao porto. |
| GET | `/api/lotes/{id}/leituras` | Histórico de leituras do lote (para os gráficos). |
| GET | `/api/alertas` | Alertas ativos para o painel. |
| POST | `/api/sincronizar` | Buscar leituras novas no ThingSpeak e gravar no banco. |
| GET | `/api/publico/{codigo}` | Visão pública do lote (consumidor, via QR Code). |
| GET | `/api/laudos/{token}` | Laudo completo do lote (produtor e importador). |

---

### GET `/api/saude`

```json
{ "status": "ok" }
```

---

### GET `/api/frutas`

Valores iniciais que o backend grava na primeira execução (todos editáveis depois):

```json
[
  {
    "id": "uva",
    "nome": "Uva de mesa",
    "temp_min_c": 0.0,
    "temp_max_c": 2.0,
    "umidade_min_pct": 85.0,
    "umidade_max_pct": 95.0,
    "risco_no_frio": null,
    "fonte": "Embrapa Semiárido, Cultivo da videira (Lima, 2016)"
  },
  {
    "id": "manga",
    "nome": "Manga",
    "temp_min_c": 10.0,
    "temp_max_c": 13.0,
    "umidade_min_pct": 85.0,
    "umidade_max_pct": 90.0,
    "risco_no_frio": "corte negro",
    "fonte": "USDA, Agriculture Handbook 66 (Paull e Chen, 2016); Embrapa Semiárido, Cultivo da mangueira (Assis, 2015)"
  }
]
```

> **Em decisão:** o teto inicial da uva. A Embrapa recomenda 0 °C (uva sem semente) e
> 2 °C (com semente); o slide 7 usa 4 °C, valor sem fonte encontrada. O contrato não
> muda com a escolha, só o valor inicial. Ver [Referências](#referências).

---

### POST `/api/frutas`

Corpo (todos os campos obrigatórios, menos `risco_no_frio`):

```json
{
  "id": "melao",
  "nome": "Melão",
  "temp_min_c": 2.0,
  "temp_max_c": 5.0,
  "umidade_min_pct": 90.0,
  "umidade_max_pct": 95.0,
  "risco_no_frio": null,
  "fonte": "Referência da faixa"
}
```

- `id`: identificador curto, só letras minúsculas sem acento, números, `-` ou `_`.
  Não pode repetir um que já exista.
- `temp_min_c` menor que `temp_max_c`; `umidade_min_pct` menor que
  `umidade_max_pct`, as duas entre 0 e 100.
- `risco_no_frio`: opcional. Nome do dano que o frio abaixo do piso causa na fruta,
  usado no alerta ("risco de corte negro"). Sem ele, o alerta de frio só diz a ação.

Resposta `201`: a fruta criada. Resposta `400` se algum campo for inválido:

```json
{ "erro": "temp_min_c precisa ser menor que temp_max_c." }
```

---

### PUT `/api/frutas/{id}`

Mesmo corpo do `POST`, sem o campo `id`. Os campos substituem os anteriores (se
`risco_no_frio` não vier, ele fica `null`). Resposta `200`: a fruta atualizada. Resposta `400` nas mesmas regras do
`POST`, `404` se a fruta não existir.

A edição não altera os lotes já cadastrados (ver "Cópia da faixa no lote" em
Conceitos). Não há rota para apagar fruta, porque lotes antigos apontam para ela.

---

### GET `/api/lotes`

Lista do mais recente para o mais antigo. O campo `risco` é um resumo; o detalhe está em
`GET /api/lotes/{id}`.

```json
[
  {
    "id": 3,
    "fruta": "uva",
    "produtor": "Sítio Boa Vista",
    "origem": "Packing house Petrolina",
    "porto_destino": "Suape",
    "inicio": "2026-10-24T09:00:00Z",
    "fim": null,
    "status": "em_transito",
    "codigo_publico": "q7Rk2xWm",
    "faixa_segura": {
      "temp_min_c": 0.0,
      "temp_max_c": 2.0,
      "umidade_min_pct": 85.0,
      "umidade_max_pct": 95.0
    },
    "risco": {
      "nivel": "LARANJA",
      "graus_hora_acima": 24.3,
      "graus_hora_abaixo": 0.0
    }
  }
]
```

`status` vale `em_transito` (sem `fim`) ou `encerrado`. `faixa_segura` é a cópia
gravada no lote quando ele foi criado. Lote sem nenhuma leitura vem
com `risco.nivel` igual a `SEM_DADOS` e os dois graus-hora iguais a `0`.

---

### POST `/api/lotes`

Corpo:

```json
{
  "fruta": "uva",
  "produtor": "Sítio Boa Vista",
  "origem": "Packing house Petrolina",
  "porto_destino": "Suape",
  "inicio": "2026-10-24T09:00:00Z"
}
```

- `fruta`: obrigatório, um dos `id` de `GET /api/frutas`.
- `produtor`, `origem` e `porto_destino`: obrigatórios, texto livre.
- `inicio`: opcional. Se não vier, vale o horário atual.
- `faixa_segura`: opcional, para um lote com faixa própria (ex.: cultivar mais
  sensível). Mesmos quatro campos de `GET /api/frutas`, com as mesmas regras de
  validação. Se não vier, o lote copia a faixa atual da fruta.

Resposta `201`: o lote criado, no mesmo formato de um item de `GET /api/lotes`. O
`codigo_publico` e o `token_laudo` são gerados aqui; o token só aparece em
`GET /api/lotes/{id}`.

Resposta `400`:

```json
{ "erro": "Fruta 'abacaxi' não cadastrada. Use: uva, manga." }
```

Regra de um lote ativo: existe um único canal do ThingSpeak (um sensor), então só pode
haver um lote `em_transito` por vez. Criar outro antes de encerrar o atual devolve `400`:

```json
{ "erro": "O lote 3 ainda está em trânsito. Encerre-o antes de cadastrar outro." }
```

---

### GET `/api/lotes/{id}`

O lote com a análise completa da viagem até agora.

```json
{
  "id": 3,
  "fruta": "uva",
  "produtor": "Sítio Boa Vista",
  "origem": "Packing house Petrolina",
  "porto_destino": "Suape",
  "inicio": "2026-10-24T09:00:00Z",
  "fim": null,
  "status": "em_transito",
  "codigo_publico": "q7Rk2xWm",
  "token_laudo": "Zp4c0bW9tQ1yHs8LkV2nRA",
  "faixa_segura": {
    "temp_min_c": 0.0,
    "temp_max_c": 2.0,
    "umidade_min_pct": 85.0,
    "umidade_max_pct": 95.0
  },
  "analise": {
    "amostras": 1240,
    "amostras_fora_faixa": 96,
    "primeira_leitura": "2026-10-24T09:00:12Z",
    "ultima_leitura": "2026-10-25T17:29:40Z",
    "temp_min_c": 1.2,
    "temp_max_c": 9.8,
    "temp_media_c": 2.9,
    "graus_hora_acima": 24.3,
    "graus_hora_abaixo": 0.0,
    "nivel_acima": "LARANJA",
    "nivel_abaixo": "VERDE",
    "nivel": "LARANJA",
    "recomendacao": "Abuso relevante. Inspeção física obrigatória antes do embarque.",
    "trechos_fora_faixa": [
      {
        "inicio": "2026-10-24T20:30:00Z",
        "fim": "2026-10-25T02:10:00Z",
        "duracao_min": 340.0,
        "lado": "acima",
        "temp_extrema_c": 9.8
      }
    ],
    "eventos_porta": [
      {
        "inicio": "2026-10-24T21:00:20Z",
        "fim": "2026-10-24T21:40:00Z",
        "duracao_min": 39.7,
        "lux_max": 880.0
      }
    ]
  }
}
```

`amostras_fora_faixa` conta só a temperatura: leituras abaixo de `temp_min_c` ou acima
de `temp_max_c` da fruta (mesmo critério do `fora_faixa_termica` do
`eda_plantsync.py`). Umidade fora da faixa aparece por leitura em
`GET /api/lotes/{id}/leituras`, campo `fora_faixa_umidade`, e não entra nessa conta.

- `trechos_fora_faixa`: cada trecho tem `lado` (`acima` ou `abaixo`) e
  `temp_extrema_c`, a temperatura mais distante da faixa no trecho (a maior, se acima; a
  menor, se abaixo). Trecho de uma leitura só tem `duracao_min` igual a `0`.

Lote sem leituras: `analise.amostras` é `0`, os três níveis são `SEM_DADOS`, os campos
de temperatura e as datas de leitura vêm `null`, e `trechos_fora_faixa` e
`eventos_porta` vêm vazios.

Resposta `404` se o lote não existir.

---

### POST `/api/lotes/{id}/encerrar`

Marca a chegada. Corpo opcional:

```json
{ "fim": "2026-10-25T18:00:00Z" }
```

Sem corpo, `fim` vale o horário atual. Resposta `200`: o lote no formato de
`GET /api/lotes`. Resposta `400` se o lote já estiver encerrado ou se `fim` for anterior
ao `inicio`.

---

### GET `/api/lotes/{id}/leituras`

Leituras do lote em ordem cronológica, já com as marcações que o gráfico precisa.

```json
[
  {
    "data_hora": "2026-10-24T21:00:20Z",
    "temperatura_c": 6.4,
    "umidade_pct": 82.0,
    "luminosidade_lux": 640.0,
    "fora_faixa_temp": true,
    "fora_faixa_umidade": true,
    "porta_aberta": true
  }
]
```

- `porta_aberta` é `true` quando a luminosidade passa de 300 lux (mesmo limiar do
  pipeline analítico). Fica `false` quando a luminosidade é `null`.
- Leituras descartadas pela auditoria (temperatura fisicamente impossível, abaixo de
  -40 °C ou acima de 80 °C) não aparecem.

---

### GET `/api/alertas`

Alertas dos lotes em trânsito, do mais grave para o mais leve. Dois tipos:

- `risco_termico`: um alerta para cada lado da faixa com nível `AMARELO`, `LARANJA` ou
  `VERMELHO`. O campo `lado` diz se é calor (`acima`) ou frio (`abaixo`).
- `porta_aberta`: abertura de porta detectada durante a viagem.

```json
[
  {
    "lote_id": 3,
    "fruta": "uva",
    "tipo": "risco_termico",
    "lado": "acima",
    "nivel": "LARANJA",
    "mensagem": "Lote 3 (uva) acumulou 24 °C·h acima de 2 °C: inspecionar antes do embarque.",
    "data_hora": "2026-10-25T17:29:40Z"
  },
  {
    "lote_id": 3,
    "fruta": "uva",
    "tipo": "porta_aberta",
    "lado": null,
    "nivel": "AMARELO",
    "mensagem": "Lote 3 (uva): porta aberta por 40 min às 18:00 de 24/10.",
    "data_hora": "2026-10-24T21:00:20Z"
  }
]
```

Exemplo de alerta de frio, para um lote de manga (`risco_no_frio` = "corte negro"):

```json
{
  "lote_id": 4,
  "fruta": "manga",
  "tipo": "risco_termico",
  "lado": "abaixo",
  "nivel": "VERMELHO",
  "mensagem": "Lote 4 (manga) acumulou 108 °C·h abaixo de 10 °C: risco de corte negro, redirecionar para mercado interno ou processamento.",
  "data_hora": "2026-10-27T09:00:00Z"
}
```

Se a fruta não tiver `risco_no_frio`, o trecho "risco de ..., " não aparece.

Ação no texto da mensagem por nível: `AMARELO` → "priorizar na expedição",
`LARANJA` → "inspecionar antes do embarque", `VERMELHO` → "redirecionar para mercado
interno ou processamento". O horário escrito dentro da mensagem de porta aberta já vem
no fuso de Recife (no exemplo, `21:00:20Z` vira "18:00"); o campo `data_hora` continua
em UTC.

---

### POST `/api/sincronizar`

Busca no ThingSpeak as leituras do canal configurado e grava no banco as que ainda não
existem (a chave é o `entry_id` do ThingSpeak, então repetir a chamada não duplica nada).
Sem corpo.

```json
{
  "canal": 3493443,
  "recebidas": 100,
  "novas": 12,
  "descartadas": 1
}
```

- `recebidas`: quantas leituras o ThingSpeak devolveu.
- `novas`: quantas foram gravadas agora.
- `descartadas`: quantas a auditoria rejeitou (sem temperatura ou com valor
  fisicamente impossível).

Resposta `502` se o ThingSpeak estiver fora do ar.

### GET `/api/publico/{codigo}`

Visão do consumidor, aberta pelo QR Code da caixa. Mostra só quem produziu, de onde veio
e o selo. **Nunca** traz curva, temperaturas, graus-hora ou nível de risco.

```json
{
  "fruta": "Manga",
  "produtor": "Sítio Boa Vista",
  "origem": "Packing house Petrolina",
  "selo_faixa_segura": true
}
```

`selo_faixa_segura` é `true` só quando as três condições valem juntas:

1. o lote já foi encerrado (chegou ao porto);
2. o lote tem leituras;
3. `nivel_acima` e `nivel_abaixo` são `VERDE`.

Em qualquer outro caso é `false`. O painel mostra o selo "Transportado dentro da faixa
segura" só quando é `true`. `VERDE` aceita desvio marginal (menos de 5 °C·h), conforme a
tabela de níveis.

Resposta `404` se o código não existir:

```json
{ "erro": "Código não encontrado." }
```

---

### GET `/api/laudos/{token}`

Laudo completo, para o produtor e o importador. O formato é o de `GET /api/lotes/{id}`
(lote, faixa e `analise` com os graus-hora dos dois lados, níveis e
`trechos_fora_faixa`), sem o `token_laudo`, mais a curva da viagem no campo `leituras`,
no formato de `GET /api/lotes/{id}/leituras`:

```json
{
  "id": 3,
  "fruta": "uva",
  "produtor": "Sítio Boa Vista",
  "...": "demais campos do lote e a analise, como em GET /api/lotes/{id}",
  "leituras": [
    {
      "data_hora": "2026-10-24T21:00:20Z",
      "temperatura_c": 6.4,
      "umidade_pct": 82.0,
      "luminosidade_lux": 640.0,
      "fora_faixa_temp": true,
      "fora_faixa_umidade": true,
      "porta_aberta": true
    }
  ]
}
```

Resposta `404` se o token não existir, com a mesma mensagem do código público
("Código não encontrado."), para não dar pistas de quais códigos existem.

---

## Campos do ThingSpeak usados

Mapeamento do canal 3493443, conforme o `README.md`:

| Campo | Grandeza | Uso no backend |
|---|---|---|
| `field1` | Temperatura (°C) | Graus-hora, faixa segura. |
| `field2` | Umidade relativa (%) | Faixa segura. |
| `field5` | Luminosidade (lux) | Porta aberta. |

## Limitações conhecidas

- **Um sensor, um lote por vez.** As leituras vão para o lote pelo horário, e há um só
  canal do ThingSpeak. Por isso a API aceita apenas um lote em trânsito de cada vez
  (ver `POST /api/lotes`). Para acompanhar cargas simultâneas, cada lote precisaria do
  seu próprio sensor e canal, e o lote passaria a guardar o número do canal.

- **Token sem login.** Enquanto não houver login (RF07), qualquer um com acesso ao painel
  interno vê o `token_laudo` em `GET /api/lotes/{id}`. Com o login, só os perfis
  autorizados passariam a vê-lo. Não há rota para trocar um token vazado.
- **Banco sem migração.** Mudanças nas tabelas exigem apagar o `plantsync.db` local; é
  aceitável num protótipo, mas um sistema em produção precisaria de migrações.

## Fora deste contrato (por enquanto)

- Login e perfis (RF07): aguardando decisão de escopo.

## Referências

ASSIS, J. S. de. Colheita e pós-colheita. In: EMBRAPA SEMIÁRIDO. **Cultivo da
mangueira**. 3. ed. Petrolina: Embrapa Semiárido, 2015. (Sistema de Produção, 2).
Disponível em:
https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1031747/1/Cultivo-da-Mangueira.pdf.
Acesso em: 25 out. 2026.

CRISOSTO, C. H.; SMILANICK, J. L. Table grape. In: GROSS, K. C.; WANG, C. Y.;
SALTVEIT, M. (ed.). **The commercial storage of fruits, vegetables, and florist and
nursery stocks**. Washington, DC: USDA, Agricultural Research Service, 2016.
(Agriculture Handbook, 66). p. 344-346. Disponível em:
https://www.ars.usda.gov/is/np/CommercialStorage/CommercialStorage.pdf. Acesso em:
25 out. 2026.

MOVIMENTO ECONÔMICO. **Pesquisa evita corte negro e rejeição de manga exportada do
Vale do São Francisco**. Recife, 21 set. 2026. Disponível em:
https://movimentoeconomico.com.br/agronegocio/2026/09/21/pesquisa-evita-corte-negro-e-rejeicao-de-manga-exportada-do-vale-do-sao-francisco/.
Acesso em: 27 out. 2026.

LIMA, M. A. C. de. Colheita e pós-colheita. In: EMBRAPA SEMIÁRIDO. **Cultivo da
videira**. 2. ed. Petrolina: Embrapa Semiárido, 2016. (Sistema de Produção, 1).
Disponível em:
https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/884525/1/Cultivo-da-Videira.pdf.
Acesso em: 25 out. 2026.

PAULL, R. E.; CHEN, C. C. Mango. In: GROSS, K. C.; WANG, C. Y.; SALTVEIT, M. (ed.).
**The commercial storage of fruits, vegetables, and florist and nursery stocks**.
Washington, DC: USDA, Agricultural Research Service, 2016. (Agriculture Handbook, 66).
p. 408-409. Disponível em:
https://www.ars.usda.gov/is/np/CommercialStorage/CommercialStorage.pdf. Acesso em:
25 out. 2026.
