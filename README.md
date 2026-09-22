# PlantSync

Sistema de telemetria de microclima para monitoramento da integridade de cargas na
cadeia de exportação de frutas do Vale do São Francisco.

> Projeto Integrador — Análise e Desenvolvimento de Sistemas, 4º Período
> Tema: Inteligência de Dados no Vale do São Francisco · UC Focal: Internet das Coisas

---

## Equipe

| Integrante | Função técnica |
|---|---|
| Davi Clemente — `@cldavii` | Hardware / IoT |
| Ygor Sampaio | Hardware / IoT |
| Jorge Antonio Figueredo — `@Jorgefigueredoo` | Backend / Cloud |
| Nicolas Tavares da Silva — `@Otoque` | Backend / Cloud |
| Pedro Valença — `@pedrohmvalenca` | FrontEnd / Documentação |

---

## Contexto

A uva de mesa e a manga exportadas pelo Vale do São Francisco dependem da manutenção de
uma faixa térmica restrita ao longo de todo o período pós-colheita. Entre a expedição na
unidade de beneficiamento e o embarque portuário, contudo, não há registro sistemático
das condições internas do compartimento de carga: elevações de temperatura, ocorrências
de condensação ou aberturas indevidas permanecem sem documentação. A constatação do dano
ocorre somente no destino, semanas após o embarque, sem evidência que permita identificar
o trecho em que a perda teve origem.

## Solução

Um nó sensor de baixo custo instalado no interior da carga. O ESP32-C3 afere temperatura
e umidade relativa e, na evolução prevista para o período, incorpora a detecção de água
livre e de luminosidade.

A inclusão da luminosidade fundamenta-se na premissa de que a incidência de luz no
interior de um compartimento lacrado indica abertura da porta, condição associada à
interrupção da cadeia do frio ou a possível violação da carga, não detectável por
sensoriamento térmico isolado.

Sobre o histórico acumulado em nuvem, a camada analítica calcula o abuso térmico
acumulado em graus-hora, correspondente à integral do excesso de temperatura em relação
ao limite seguro, e consolida o resultado em uma classificação de risco em quatro níveis,
da qual decorre a recomendação operacional sobre o lote.

---

## Estrutura

```
PlantSync/
├── firmware/plantsync-edge/    Módulo de borda (ESP32-C3)
│   ├── main.ino                Firmware v2 — 3 sensores, Fail-Fast, JSON
│   ├── diagram.json            Circuito para o simulador Wokwi
│   ├── credentials.h.example   Modelo de credenciais (credentials.h é ignorado)
│   ├── wokwi.toml
│   └── libraries.txt
├── analytics/
│   ├── eda_plantsync.py        Pipeline de análise exploratória
│   ├── requirements.txt
│   ├── data/                   CSV exportado do ThingSpeak (não versionado)
│   └── outputs/                Gráficos e relatórios gerados
├── api/
│   └── PlantSync.postman_collection.json   Testes de contrato da API
└── docs/
    ├── CHECKPOINT-01.md        Documento do checkpoint
    ├── CHECKPOINT-01.html      Versão para gerar o PDF da entrega
    └── img/                    Registro fotográfico
```

---

## Canal de telemetria

Canal público no ThingSpeak: **[3493443](https://thingspeak.mathworks.com/channels/3493443)**

| Campo | Grandeza | Origem |
|---|---|---|
| `field1` | Temperatura (°C) | protótipo de 16/09 |
| `field2` | Umidade relativa do ar (%) | protótipo de 16/09 |
| `field3` | RSSI (dBm) — integridade do enlace | protótipo de 16/09 |
| `field4` | Água livre / condensação (%) | firmware v2 |
| `field5` | Luminosidade (lux) | firmware v2 |
| `field6` | Bitmask de alertas | firmware v2 |
| `field7` | Índice de risco (0–100) | firmware v2 |

---

## Como executar

### Firmware — placa real

1. Arduino IDE com suporte à placa **ESP32-C3** instalado.
2. Instale as bibliotecas de `firmware/plantsync-edge/libraries.txt`.
3. Copie `credentials.h.example` para `credentials.h` e preencha SSID, senha e a
   Write API Key do canal.
4. Compile e grave.

> **Montagem:** o DHT11 exige resistor de **pull-up de ~10 kΩ entre DATA (GPIO 4) e
> 3V3**. Sem ele a placa trava com `Interrupt wdt timeout on CPU0` durante a leitura.
> A falha foi diagnosticada e documentada pela equipe em 31/08.

### Firmware — simulação no Wokwi

Crie um projeto ESP32 em [wokwi.com](https://wokwi.com), cole `main.ino` e substitua a
aba `diagram.json` pela deste repositório. **Descomente `#define SIMULACAO_WOKWI`** no
topo do arquivo: o simulador emula o protocolo do DHT22, que não é compatível bit a bit
com o DHT11 da montagem física.

No simulador, arraste o sensor de luz para simular a abertura da porta e o
potenciômetro para simular acúmulo de água. Os alertas acendem o LED.

### Testes de contrato da API

Importe `api/PlantSync.postman_collection.json`, preencha `WRITE_API_KEY` e
`READ_API_KEY` nas variáveis de ambiente e rode a coleção. Cinco cenários: ingestão
válida, ingestão em alerta, rejeição de credencial inválida, leitura do canal e
exportação para a camada analítica.

### Pipeline analítico

```bash
cd analytics
pip install -r requirements.txt

# Modo demonstração — viagem sintética de 72 h com falha de compressor
python eda_plantsync.py

# Com telemetria real exportada do ThingSpeak
python eda_plantsync.py --csv data/feeds.csv
```

Saídas em `analytics/outputs/`: dois gráficos PNG, relatório textual da viagem e o
dataset tratado em CSV.

---

## Segurança

Nenhuma credencial é versionada. `credentials.h` está no `.gitignore` e o repositório
contém apenas o arquivo-modelo. A coleção Postman lê as chaves de variáveis de
ambiente.

---

## Limitações reconhecidas

- **Exatidão do DHT11.** Faixa de 0–50 °C com exatidão de ~±2 °C. A cadeia do frio da
  uva exige discriminar 0–4 °C, margem equivalente à amplitude da faixa que se pretende
  controlar. Mantido como prova de conceito; migração para SHT3x ou DS18B20 prevista.
- **Alimentação cabeada.** Wi-Fi e HTTP contínuos inviabilizam operação por bateria.
  Deep sleep e rádios de baixo consumo ficam para versões futuras.
- **Gabinete sem certificação IP.** Atende à prova de conceito, não a ambiente
  industrial de lavagem pesada.

---

Projeto acadêmico desenvolvido para avaliação no Projeto Integrador do curso de
Análise e Desenvolvimento de Sistemas.
