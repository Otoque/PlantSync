# PlantSync — Checkpoint de Projeto Integrador

**Telemetria de microclima e integridade de carga para a cadeia de exportação de frutas
do Vale do São Francisco**

| | |
|---|---|
| **Tema geral** | Inteligência de Dados no Vale do São Francisco |
| **UC Focal Integradora** | Internet das Coisas (IoT) |
| **Turma** | Análise e Desenvolvimento de Sistemas — 4º Período |
| **Data** | 21 de setembro de 2026 |

> A versão para impressão e geração do PDF da entrega está em
> [`CHECKPOINT-01.html`](CHECKPOINT-01.html).

---

## 1. Identificação da Equipe e Contexto Regional

### 1.1 Equipe

| Integrante | Função técnica principal | Atuação no período |
|---|---|---|
| **Davi Clemente** (`@cldavii`) | Hardware / IoT | Especificação e homologação do ESP32-C3, montagem do nó sensor e definição da pinagem. |
| **Ygor Sampaio** | Hardware / IoT | Montagem física, ensaios de sensoriamento e validação do gabinete do protótipo. |
| **Jorge Antonio Figueredo** (`@Jorgefigueredoo`) | Backend / Cloud | Diagnóstico da camada de leitura do sensor e integração com a API de ingestão. |
| **Nicolas Tavares da Silva** (`@Otoque`) | Backend / Cloud | Canal de telemetria em nuvem, contrato REST e memorial descritivo de engenharia. |
| **Pedro Valença** (`@pedrohmvalenca`) | FrontEnd / Documentação | Camada de apresentação, governança documental e consolidação dos artefatos do checkpoint. |

### 1.2 Contexto regional atendido

O projeto atende produtores e exportadores de **uva de mesa e manga** do polo
Petrolina (PE) / Juazeiro (BA). O nó sensor é concebido para operar em três pontos da
cadeia pós-colheita: *packing houses*, câmaras de resfriamento rápido e **contêineres e
carretas refrigeradas** no trajeto até os portos de Suape e Salvador. O foco do semestre
é o elo de transporte, por ser o trecho em que hoje há menor visibilidade sobre as
condições reais da carga.

---

## 2. Status Atual do Projeto e Checklist Interdisciplinar

Legenda: `[X]` concluído · `[~]` parcialmente concluído · `[ ]` não iniciado

### IoT & Camada de Borda (UC Focal)

- **[X] Sensores definidos.** DHT11 de 4 pinos (temperatura e umidade relativa), ligado
  ao GPIO 4 do ESP32-C3 com resistor de pull-up de 10 kΩ entre DATA e 3V3. Limitação de
  exatidão identificada e tratada na Seção 8.3.
- **[X] Microcontrolador homologado.** ESP32-C3 validado por ensaio isolado de
  comunicação serial a 115200 baud antes da integração do sensor, confirmando placa,
  gravação e monitor serial operacionais.
- **[~] Payload serializado em JSON.** A ingestão em produção usa *query string* sobre
  HTTP, contrato aceito pela API da nuvem. A serialização JSON estruturada e normalizada
  está implementada na versão 2 do firmware (`ArduinoJson`), ainda em bancada.
- **[X] Testes de contrato via REST iniciados.** Requisições HTTP validadas com retorno
  de código 200 e `entry_id` incremental da nuvem. Coleção Postman com cinco cenários
  versionada no repositório.

### Integração Cloud & Infraestrutura

- **[X] Provedor e serviços definidos.** ThingSpeak como camada de ingestão primária e
  série temporal, com canal público criado e operante.
- **[~] Estratégia de banco de dados modelada.** Arquitetura em duas camadas decidida:
  série temporal no ThingSpeak para telemetria bruta e persistência relacional
  (PostgreSQL / Supabase) para histórico consolidado. Modelagem física das tabelas ainda
  não escrita.

### Data Science & Inteligência de Safra

- **[ ] Fontes de dados climáticos históricos mapeadas.** Não iniciado. Candidatas
  levantadas para o próximo ciclo: INMET (estações de Petrolina) e Embrapa Semiárido.
- **[~] Scripts de limpeza e análise exploratória estruturados.** Pipeline em
  Python/Pandas implementado e executando: auditoria de qualidade, tratamento de
  duplicatas e outliers, cálculo de graus-hora de abuso térmico, detecção de anomalias e
  classificação de risco da carga. Validado com série sintética; aguarda volume
  suficiente de telemetria real.

### Segurança da Informação & Qualidade

- **[~] Política de acesso e proteção de API Keys.** Proteção de credenciais
  *implementada*: chaves isoladas em `credentials.h`, excluídas do versionamento por
  `.gitignore` e distribuídas por arquivo-modelo. O RBAC de perfis de usuário depende da
  camada de aplicação, ainda não iniciada.
- **[X] Estratégia de testes de firmware e de contrato em elaboração.** Padrão Fail-Fast
  em operação no firmware, com validação em dois estágios (`isnan` e faixa física do
  sensor). Testes de contrato cobrem ingestão válida, ingestão em alerta, rejeição de
  credencial inválida e leitura.

### Gestão e Repositório

- **[X] Repositório oficial no GitHub configurado.** Repositório da equipe ativo, com
  quatro contas colaboradoras e histórico de commits distribuído. Frentes exploratórias
  mantidas em repositórios satélites (Seção 7).
- **[ ] Backlog de tarefas / Kanban ativo.** Não iniciado. Coordenação feita até aqui por
  canal de mensagens e divisão informal de frentes. Abertura do GitHub Projects é meta do
  próximo checkpoint.

### 2.1 Estágio global da equipe

```
( ) Planejamento e Arquitetura
( ) Levantamento e Refinamento de Requisitos
(X) Prototipagem da Borda (IoT)              <- estágio predominante
(→) Integração Nuvem / Pipeline Inicial      <- em transição
( ) Desenvolvimento dos Dashboards e Modelos
( ) Testes e Validação
```

A equipe encerrou o ciclo de prototipagem da borda com hardware homologado, firmware
funcional e telemetria chegando à nuvem, e inicia agora a consolidação do pipeline de
ingestão e da camada analítica.

---

## 3. Problema Regional e Proposta de Solução

### 3.1 Problema focal

A uva de mesa e a manga exportadas pelo Vale do São Francisco dependem de uma faixa
térmica estreita para chegar íntegras à Europa e aos Estados Unidos, e todo o valor
agregado na lavoura pode ser perdido em poucas horas de desvio na cadeia do frio. O
problema não é apenas o desvio acontecer, mas ser **invisível**: entre a saída do packing
house e o embarque no porto, o produtor não tem registro de quando a temperatura subiu,
por quanto tempo permaneceu fora da faixa, se houve condensação sobre a fruta ou se o
contêiner foi aberto indevidamente em trânsito. A quebra só é descoberta semanas depois,
no destino, quando a carga é rejeitada ou desvalorizada — sem evidência para identificar
o trecho responsável, corrigir o processo ou sustentar qualquer discussão contratual com
o transportador.

### 3.2 Solução proposta

O PlantSync instala um nó sensor de baixo custo dentro do ambiente da carga. Um
microcontrolador ESP32-C3 lê temperatura e umidade relativa do ar e, na evolução prevista
para este semestre, acrescenta um sensor de umidade para detectar água livre e
condensação e um sensor de luminosidade. A luminosidade é o diferencial conceitual da
solução: **luz dentro de um contêiner lacrado significa porta aberta** — ou seja, quebra
da cadeia do frio ou violação da carga, um evento que sensor térmico nenhum identifica
isoladamente. Cada leitura passa por validação na própria borda: amostra inconsistente é
descartada antes de sair do dispositivo, de modo que a base em nuvem nunca recebe dado
corrompido.

A telemetria validada sobe por REST para o ThingSpeak, que atua como camada de ingestão e
série temporal, alimentando painéis em tempo real. Sobre esse histórico, a camada
analítica em Python converte a série bruta em decisão: calcula os **graus-hora de abuso
térmico** — a integral do excesso de temperatura no tempo, métrica usada na indústria
para estimar perda de vida útil —, detecta anomalias por desvio móvel, identifica eventos
de abertura de porta e consolida tudo em um farol operacional de quatro níveis. O
resultado não é um gráfico a mais para o gestor interpretar, e sim uma recomendação
direta sobre o que fazer com aquele lote: liberar, priorizar na expedição, inspecionar
antes do embarque ou redirecionar para o mercado interno.

---

## 4. Delimitação de Escopo (4º Período)

### 4.1 Dentro do escopo

| # | Entrega obrigatória do semestre |
|---|---|
| **E1** | **Módulo IoT de borda.** ESP32-C3 com DHT11, sensor de umidade e sensor de luminosidade, leitura periódica, validação Fail-Fast, serialização JSON e envio por HTTP REST com credenciais protegidas. |
| **E2** | **Pipeline de ingestão em nuvem.** Canal ThingSpeak recebendo e persistindo a telemetria em série temporal, com contrato de API validado por testes automatizados no Postman. |
| **E3** | **Painel de acompanhamento com alertas.** Interface web exibindo curvas históricas e destacando visualmente as amostras fora da faixa segura de conservação. |
| **E4** | **Módulo analítico preliminar em Python.** Limpeza e auditoria de qualidade dos dados, cálculo de graus-hora de abuso térmico, detecção de anomalias térmicas e classificação de risco do lote. |
| **E5** | **Governança de segurança e qualidade.** Proteção de credenciais fora do versionamento, testes de contrato da API e documentação técnica reprodutível do protótipo. |

### 4.2 Fora do escopo

| Item | Justificativa |
|---|---|
| Aplicativo mobile nativo com operação offline | A camada de apresentação do semestre é web. Sincronização offline exigiria estratégia própria de resolução de conflitos. |
| Atuação automatizada sobre compressores e equipamentos de refrigeração | A solução é de monitoramento e apoio à decisão. Atuar sobre equipamento industrial envolve segurança operacional e certificação fora do alcance acadêmico. |
| Integração com sistemas aduaneiros portuários em tempo real | Depende de convênio institucional e credenciamento junto aos portos. |
| Conectividade LoRaWAN / NB-IoT e autonomia por bateria | Limitação real do protótipo atual, mas o redesenho energético e de rádio extrapola o período. |
| Certificação formal de grau de proteção (IP) do gabinete | O invólucro atual atende à prova de conceito; certificação exige ensaio laboratorial. |

---

## 5. Levantamento de Requisitos (Visão Interdisciplinar)

### 5.1 Requisitos funcionais

**RF01 — IoT / Borda.** O módulo IoT deve coletar leituras periódicas de temperatura e
umidade relativa em intervalo configurável e serializar os dados em formato JSON
estruturado, contendo identificação do dispositivo, identificação do lote, número de
sequência e bloco de leituras.

**RF02 — IoT / Borda.** O módulo IoT deve detectar a abertura indevida do compartimento
de carga por meio da leitura de luminosidade interna, sinalizando o evento quando o valor
medido ultrapassar o limiar configurado para ambiente lacrado.

**RF03 — Cloud / Ingestão.** O sistema deve receber e persistir a telemetria enviada
pelos dispositivos de borda em estrutura de série temporal, preservando o instante de
cada amostra e devolvendo confirmação de gravação ao dispositivo.

**RF04 — Alertas.** O sistema deve emitir alerta quando qualquer parâmetro monitorado
sair da faixa segura de conservação, tanto localmente no dispositivo quanto na camada de
apresentação. Os alertas devem ser combináveis, permitindo que múltiplas condições
críticas sejam sinalizadas simultaneamente em uma mesma amostra.

**RF05 — Data / BI.** O painel deve exibir as curvas históricas de temperatura e umidade
do lote, destacar visualmente as amostras fora da faixa segura e apresentar o cálculo
acumulado de anomalia térmica do trajeto.

**RF06 — Data Science.** O módulo analítico deve auditar a qualidade da série recebida —
identificando duplicatas de retransmissão, lacunas de amostragem, valores nulos e
outliers — e classificar o lote em faixas de risco a partir dos graus-hora de abuso
térmico acumulados, emitindo a recomendação operacional correspondente.

**RF07 — Acesso.** O sistema deve autenticar usuários e diferenciar permissões por
perfil, distinguindo ao menos o Operador Logístico, que acompanha as cargas em trânsito,
do Gestor de Agronegócio, que consulta o histórico consolidado dos lotes.

### 5.2 Requisitos não funcionais

**RNF01 — Resiliência / IoT.** O firmware deve aplicar o padrão **Fail-Fast** em dois
estágios: abortar o envio quando a leitura retornar `isnan`, e também quando o valor,
embora numericamente válido, estiver fora da faixa física de operação do sensor. O
segundo estágio é indispensável porque um sensor degradado devolve valores plausíveis ao
tipo de dado, mas impossíveis ao fenômeno — que entrariam na base com aparência de dado
bom.

**RNF02 — Segurança.** Credenciais de rede e chaves de API não devem constar em
código-fonte versionado. Devem residir em arquivo de configuração local excluído do
controle de versão, distribuído à equipe por arquivo-modelo sem valores reais. O tráfego
de telemetria deve ocorrer sobre HTTPS/TLS.

**RNF03 — Desempenho / Cota.** O ciclo de envio deve usar temporização não bloqueante
baseada em `millis()`, sem `delay()` no laço principal, respeitando a janela mínima de
ingestão imposta pela API de nuvem. O dispositivo deve permanecer responsivo a leituras
locais e à sinalização de alerta entre um envio e outro.

**RNF04 — Disponibilidade / Rede.** O firmware deve detectar a queda do enlace Wi-Fi e
restabelecer a conexão automaticamente, sem intervenção física e sem reinicialização da
placa, retomando o ciclo de telemetria no intervalo seguinte.

**RNF05 — Observabilidade.** O dispositivo deve registrar em log serial cada leitura,
cada descarte por validação e o resultado de cada requisição à nuvem, incluindo
contadores acumulados de amostras lidas, descartadas e enviadas, permitindo auditar em
campo a taxa de aproveitamento do sensor.

---

## 6. Arquitetura Preliminar e Fluxo de Dados

```
┌──────────────────────────────┐    ┌──────────────────────────┐    ┌────────────────────────┐
│  BORDA — dentro da carga     │    │  NUVEM                   │    │  ANÁLISE E APRESENTAÇÃO│
├──────────────────────────────┤    ├──────────────────────────┤    ├────────────────────────┤
│  ESP32-C3                    │    │  ThingSpeak              │    │  Python / Pandas       │
│   ├─ DHT11 · GPIO 4          │    │   ├─ Ingestão REST       │    │   ├─ Auditoria de dados│
│   │   temperatura + umidade  │    │   ├─ Série temporal      │    │   ├─ Graus-hora de     │
│   ├─ Sensor de umidade       │    │   │   field1..field7     │    │   │   abuso térmico    │
│   │   água livre/condensação │    │   ├─ Regras e alertas    │    │   ├─ Detecção de       │
│   ├─ LDR — luminosidade      │    │   │                      │    │   │   anomalias        │
│   │   detecção porta aberta  │    │   ├─ Persistência        │    │   └─ Farol de decisão  │
│   ├─ Validação Fail-Fast     │    │   │   PostgreSQL ······· │    │                        │
│   │   1. isnan  2. faixa     │    │   │   (previsto)         │    │  Dashboard web ······· │
│   └─ LED de alerta local     │    │   └─ Credenciais         │    │  (previsto)            │
│                              │    │       protegidas         │    │                        │
└──────────────┬───────────────┘    └────────────┬─────────────┘    └───────────┬────────────┘
               │                                 │                              │
               │  JSON · HTTPS · REST            │  REST (JSON / CSV)           │
               │  a cada 20 s                    │                              │
               └─────────────────►───────────────┴──────────────►───────────────┘
                                                 │
                                                 ▼
                    ┌────────────────────────────────────────────────────┐
                    │         DECISÃO LOGÍSTICA SOBRE O LOTE             │
                    │  Liberar · Priorizar expedição ·                   │
                    │  Inspecionar antes do embarque · Redirecionar      │
                    └────────────────────────────────────────────────────┘

   Linha contínua: implementado e operante   ·   (previsto): próximo checkpoint
```

> **Decisão arquitetural registrada.** A ingestão usa REST sobre HTTPS em vez de MQTT.
> O nó opera alimentado por cabo e envia uma amostra a cada 20 segundos, regime em que o
> ganho de eficiência do MQTT não compensa a necessidade de manter um broker próprio. A
> migração para MQTT passa a ser justificada quando o projeto evoluir para operação a
> bateria com rádio de baixo consumo, cenário explicitamente colocado fora do escopo
> deste semestre.

---

## 7. Evidências do Andamento Técnico

### 7.1 Repositórios da equipe

| Repositório | Papel | Conteúdo comprobatório |
|---|---|---|
| [Otoque/PlantSync](https://github.com/Otoque/PlantSync) | **Oficial** | Monorepo da equipe. Estrutura de back-end, front-end, hardware e documentação. Quatro contas colaboradoras com branches nominais. |
| [Otoque/Prot-tipo_IoT_16-09](https://github.com/Otoque/Prot-tipo_IoT_16-09) | Protótipo funcional | Firmware integrado com envio à nuvem, arquivo-modelo de credenciais, registro fotográfico e memorial descritivo de engenharia. |
| [Jorgefigueredoo/Temperatura-e-Umidade-ESP32-c3](https://github.com/Jorgefigueredoo/Temperatura-e-Umidade-ESP32-c3) | Ensaio de sensor | Teste isolado de leitura do DHT11 documentado, com registro da ressalva de montagem sem resistor de pull-up. |

### 7.2 Registro fotográfico do protótipo

![Protótipo PlantSync montado em protoboard](img/prototipo-fisico.jpeg)

*Figura 2 — Nó sensor montado em protoboard: ESP32-C3 alimentado por USB-C e DHT11
ligado ao GPIO 4.*

### 7.3 Canal de telemetria em nuvem

Canal público: **[thingspeak.mathworks.com/channels/3493443](https://thingspeak.mathworks.com/channels/3493443)**

> 🔲 *Inserir print do canal exibindo os gráficos com telemetria recente.*

### 7.4 Logs seriais e validação do contrato REST

> 🔲 *Inserir print do Monitor Serial mostrando as leituras, o payload e o código HTTP de retorno.*
>
> 🔲 *Inserir print do Postman com os testes de contrato aprovados.*

### 7.5 Relatório de diagnóstico de hardware

A equipe produziu um relatório técnico de nove páginas documentando a depuração da camada
de leitura do sensor, com registro de ambiente, bibliotecas, erros observados, hipóteses
levantadas e testes de isolamento conduzidos. O documento integra os anexos desta entrega
e evidencia o método de investigação adotado — descrito na Seção 8.3.

### 7.6 Organização e reuniões técnicas

> 🔲 *Inserir print das reuniões técnicas da equipe ou do quadro de tarefas.*

---

## 8. Planejamento das Próximas Entregas

### 8.1 Concluído até o momento

1. Homologação do ESP32-C3, validada por ensaio isolado de comunicação serial antes da
   integração de qualquer sensor.
2. Integração do DHT11 no GPIO 4 com resistor de pull-up, com leitura de temperatura e
   umidade em operação.
3. Firmware com reconexão automática de rede, temporização não bloqueante e validação
   Fail-Fast das leituras.
4. Canal de telemetria criado na nuvem e contrato REST validado, com retorno de
   confirmação de gravação.
5. Proteção de credenciais implementada e memorial descritivo de engenharia publicado,
   incluindo as limitações técnicas reconhecidas do protótipo.

### 8.2 Em andamento técnico

1. Consolidação das três frentes de repositório no monorepo oficial da equipe,
   organizando firmware, camada analítica e documentação sob uma estrutura única.
2. Evolução do firmware para incorporar o sensor de umidade e o sensor de luminosidade,
   com serialização JSON estruturada e motor de regras de faixa segura.
3. Pipeline analítico em Python/Pandas, com auditoria de qualidade, cálculo de graus-hora
   de abuso térmico e classificação de risco do lote.

### 8.3 Riscos técnicos reconhecidos

**⚠️ Exatidão do DHT11 é insuficiente para a faixa alvo.** A cadeia do frio da uva de
mesa exige discriminar temperaturas entre 0 °C e 4 °C. O DHT11 opera a partir de 0 °C e
tem exatidão declarada de aproximadamente ±2 °C, margem da mesma ordem de grandeza da
faixa inteira que se pretende controlar — o sensor não distingue com confiança uma carga
a 2 °C de uma carga a 4 °C, e não mede abaixo de zero. *Mitigação:* o DHT11 permanece
válido como prova de conceito do fluxo ponta a ponta; a migração para sensor calibrado de
maior exatidão (família SHT3x ou DS18B20) entra como meta do próximo checkpoint, sem
alteração do contrato de dados já estabelecido.

**⚠️ Travamento por watchdog na leitura do sensor.** Durante a integração inicial, a
placa reiniciava com `Interrupt wdt timeout on CPU0` exatamente na chamada de leitura do
sensor. A equipe conduziu o isolamento de forma metódica: validou primeiro o
microcontrolador sozinho, depois repetiu a falha sem a biblioteca de terceiros —
confirmando que a causa estava na camada física e não no software — e registrou em
relatório a ressalva da montagem sem resistor de pull-up. O protocolo de dreno aberto
usado pelo sensor exige esse resistor: sem ele a linha de dados fica flutuando, o sensor
não consegue impor a borda de resposta e a rotina de leitura permanece em espera até o
watchdog reiniciar a placa. *Situação:* resolvido com a inclusão do pull-up; a lição
ficou incorporada à documentação de montagem.

**⚠️ Dependência de alimentação cabeada.** O uso contínuo de Wi-Fi e HTTP inviabiliza a
operação prolongada por bateria, o que hoje prende o nó a uma fonte USB. *Mitigação:*
limitação assumida e declarada fora do escopo do semestre. A avaliação de ciclos de
*deep sleep* e de rádios de baixo consumo fica registrada como evolução de arquitetura
para versões futuras.

### 8.4 Previsão para o próximo checkpoint

1. Gravar na placa a versão 2 do firmware, com os três sensores integrados, e sustentar
   uma janela contínua de telemetria real que alimente a camada analítica com volume
   estatisticamente útil.
2. Executar o pipeline analítico sobre a telemetria real coletada, substituindo a série
   sintética de validação, e calibrar os limiares do farol de decisão.
3. Publicar o painel web consumindo o canal de telemetria, com curvas históricas e
   destaque visual das amostras fora da faixa segura.
4. Implementar a persistência consolidada em banco relacional e a autenticação com
   perfis distintos de Operador Logístico e Gestor de Agronegócio.
5. Abrir o quadro de tarefas no GitHub Projects e mapear as fontes de dados climáticos
   históricos do INMET e da Embrapa Semiárido para a correlação de safra.

---

*PlantSync · Checkpoint de Projeto Integrador · ADS 4º Período · 21 de setembro de 2026*
