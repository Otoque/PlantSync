# Contrato da API do PlantSync

Versão 0.2 (rascunho, 25/10/2026). Este documento descreve o que o backend entrega ao
painel web. Qualquer mudança aqui precisa ser combinada com a frente do frontend.

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
| 400 | Dado inválido no corpo da requisição. |
| 404 | Lote inexistente. |
| 502 | O ThingSpeak não respondeu ou respondeu com erro. |

## Conceitos

- **Lote**: uma carga de fruta que sai de uma origem (packing house) para um porto. Tem
  início e, quando chega, fim.
- **Leitura**: uma amostra enviada pelo sensor ao ThingSpeak (a cada 20 s). O backend
  copia as leituras para o banco local.
- **Associação leitura → lote**: uma leitura pertence ao lote quando o horário dela está
  entre o `inicio` e o `fim` do lote. Lote sem `fim` (ainda em trânsito) recebe tudo
  que chegar depois do `inicio`.
- **Faixa segura**: limites de temperatura e umidade de cada fruta, com a fonte.
- **Graus-hora (°C·h)**: soma, ao longo da viagem, de quanto a temperatura passou do
  limite superior da faixa, multiplicado pelo tempo em que ficou assim. Exemplo: 2 °C
  acima do limite durante 3 h somam 6 °C·h.
- **Nível de risco**: classificação do lote a partir dos graus-hora, em quatro níveis,
  com a recomendação operacional. Mesmos limiares do `analytics/eda_plantsync.py`:

| Nível | Graus-hora | Recomendação |
|---|---|---|
| `VERDE` | menos de 5 | Cadeia do frio íntegra ou desvio marginal. Carga liberada. |
| `AMARELO` | de 5 a menos de 20 | Abuso térmico moderado. Priorizar esta carga na expedição. |
| `LARANJA` | de 20 a menos de 50 | Abuso relevante. Inspeção física obrigatória antes do embarque. |
| `VERMELHO` | 50 ou mais | Abuso severo. Redirecionar para mercado interno ou processamento. |

> Os limiares acima foram definidos pela equipe no pipeline analítico e ainda precisam
> ser validados com um produtor parceiro.

## Endpoints

| Método | Rota | Para que serve |
|---|---|---|
| GET | `/api/saude` | Verificar se a API está no ar. |
| GET | `/api/frutas` | Listar as frutas e suas faixas seguras. |
| GET | `/api/lotes` | Listar os lotes com o resumo de risco. |
| POST | `/api/lotes` | Cadastrar um lote. |
| GET | `/api/lotes/{id}` | Ver um lote com a análise completa. |
| POST | `/api/lotes/{id}/encerrar` | Marcar a chegada do lote ao porto. |
| GET | `/api/lotes/{id}/leituras` | Histórico de leituras do lote (para os gráficos). |
| GET | `/api/alertas` | Alertas ativos para o painel. |
| POST | `/api/sincronizar` | Buscar leituras novas no ThingSpeak e gravar no banco. |

---

### GET `/api/saude`

```json
{ "status": "ok" }
```

---

### GET `/api/frutas`

Os valores definitivos virão da fonte citada no campo `fonte`.

```json
[
  {
    "id": "uva",
    "nome": "Uva de mesa",
    "temp_min_c": 0.0,
    "temp_max_c": 4.0,
    "umidade_min_pct": 85.0,
    "umidade_max_pct": 95.0,
    "fonte": "Referência bibliográfica da faixa"
  },
  {
    "id": "manga",
    "nome": "Manga",
    "temp_min_c": 10.0,
    "temp_max_c": 13.0,
    "umidade_min_pct": 85.0,
    "umidade_max_pct": 90.0,
    "fonte": "Referência bibliográfica da faixa"
  }
]
```

---

### GET `/api/lotes`

Lista do mais recente para o mais antigo. O campo `risco` é um resumo; o detalhe está em
`GET /api/lotes/{id}`.

```json
[
  {
    "id": 3,
    "fruta": "uva",
    "origem": "Packing house Petrolina",
    "porto_destino": "Suape",
    "inicio": "2026-10-24T09:00:00Z",
    "fim": null,
    "status": "em_transito",
    "risco": {
      "nivel": "LARANJA",
      "graus_hora": 24.3
    }
  }
]
```

`status` vale `em_transito` (sem `fim`) ou `encerrado`. Lote sem nenhuma leitura vem
com `risco.nivel` igual a `SEM_DADOS` e `graus_hora` igual a `0`.

---

### POST `/api/lotes`

Corpo:

```json
{
  "fruta": "uva",
  "origem": "Packing house Petrolina",
  "porto_destino": "Suape",
  "inicio": "2026-10-24T09:00:00Z"
}
```

- `fruta`: obrigatório, um dos `id` de `GET /api/frutas`.
- `origem` e `porto_destino`: obrigatórios, texto livre.
- `inicio`: opcional. Se não vier, vale o horário atual.

Resposta `201`: o lote criado, no mesmo formato de um item de `GET /api/lotes`.

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
  "origem": "Packing house Petrolina",
  "porto_destino": "Suape",
  "inicio": "2026-10-24T09:00:00Z",
  "fim": null,
  "status": "em_transito",
  "faixa_segura": {
    "temp_min_c": 0.0,
    "temp_max_c": 4.0,
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
    "graus_hora": 24.3,
    "nivel": "LARANJA",
    "recomendacao": "Abuso relevante. Inspeção física obrigatória antes do embarque.",
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

Lote sem leituras: `analise.amostras` é `0`, `nivel` é `SEM_DADOS`, os campos de
temperatura e as datas de leitura vêm `null` e `eventos_porta` vem vazio.

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

- `risco_termico`: lote com nível `AMARELO`, `LARANJA` ou `VERMELHO`.
- `porta_aberta`: abertura de porta detectada durante a viagem.

```json
[
  {
    "lote_id": 3,
    "fruta": "uva",
    "tipo": "risco_termico",
    "nivel": "LARANJA",
    "mensagem": "Lote 3 (uva) acumulou 24 °C·h acima de 4 °C: inspecionar antes do embarque.",
    "data_hora": "2026-10-25T17:29:40Z"
  },
  {
    "lote_id": 3,
    "fruta": "uva",
    "tipo": "porta_aberta",
    "nivel": "AMARELO",
    "mensagem": "Lote 3 (uva): porta aberta por 40 min às 18:00 de 24/10.",
    "data_hora": "2026-10-24T21:00:20Z"
  }
]
```

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

## Fora deste contrato (por enquanto)

- Login e perfis (RF07): aguardando decisão de escopo.
