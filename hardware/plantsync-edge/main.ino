/*
 * ============================================================================
 *  PlantSync - Modulo de Borda v3
 *  Telemetria de microclima para frutas de exportacao do Vale do Sao Francisco
 *  Projeto Integrador - ADS 4o Periodo
 * ----------------------------------------------------------------------------
 *  NOVIDADE DA v3: TRANSPORTE MQTT, SELECIONAVEL EM TEMPO DE COMPILACAO.
 *
 *  A v2 enviava telemetria exclusivamente por HTTP REST. Esta versao mantem
 *  esse caminho intacto e acrescenta MQTT ao lado dele, sob a chave
 *  USAR_MQTT. Os dois transportes consomem a MESMA amostra, ja validada pelo
 *  mesmo Fail-Fast, e sao acionados pelo MESMO temporizador nao bloqueante.
 *
 *  A escolha de manter os dois, em vez de substituir, e deliberada: permite
 *  medir um contra o outro no mesmo hardware, na mesma rede e com o mesmo
 *  payload, que e exatamente o que o trabalho de comparacao exige. Trocar o
 *  transporte de vez tornaria a comparacao impossivel de reproduzir.
 *
 *  O QUE O MQTT TRAZ QUE O HTTP NAO TEM
 *
 *    1. Sessao persistente. O handshake e pago uma vez, nao a cada envio.
 *       Medido: 34 bytes de handshake MQTT contra 884 bytes de overhead
 *       HTTP em CADA publicacao.
 *
 *    2. Last Will and Testament (LWT). O no registra, ao conectar, uma
 *       mensagem que o broker publica sozinho caso a conexao caia de forma
 *       anormal. Para cadeia do frio isso e critico: um dispositivo que
 *       emudece e um ponto cego, e ate aqui ninguem ficava sabendo. O HTTP
 *       nao tem como oferecer isso, porque nao ha sessao para morrer.
 *
 *    3. Retain. A ultima leitura fica retida no broker; quem assina depois
 *       recebe o estado corrente imediatamente, sem esperar o proximo ciclo.
 *
 *    4. QoS. O QoS 1 garante entrega ao menos uma vez, com confirmacao
 *       (PUBACK). O QoS 0 dispara e esquece.
 * ----------------------------------------------------------------------------
 *  HARDWARE (inalterado desde a v2): ESP32-C3 + DHT11 no GPIO 4.
 *
 *  NOTA DE HARDWARE - resistor de pull-up
 *  O relatorio de diagnostico de 31/08/2026 registrou travamentos do tipo
 *  "Guru Meditation Error: Core 0 panic'ed (Interrupt wdt timeout on CPU0)"
 *  durante dht.readTemperature(), com a montagem SEM resistor de pull-up.
 *  O DHT11 usa barramento 1-Wire em dreno aberto: sem o pull-up a linha DATA
 *  fica flutuando, o sensor nao consegue impor a borda de resposta e a rotina
 *  de leitura permanece em espera ocupada ate o watchdog reiniciar a placa.
 *  MANTER o resistor de ~10 kOhm entre DATA (GPIO 4) e 3V3.
 * ----------------------------------------------------------------------------
 *  Requisitos nao funcionais cobertos:
 *    RNF01 - Fail-Fast  : leitura invalida aborta o envio, nos DOIS transportes.
 *    RNF02 - Seguranca  : credenciais em credentials.h, fora do versionamento.
 *    RNF03 - Desempenho : temporizacao nao bloqueante com millis().
 *    RNF04 - Rede       : reconexao automatica de Wi-Fi e de sessao MQTT.
 * ============================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "DHT.h"
#include "credentials.h"  // WIFI_SSID, WIFI_PASSWORD, THINGSPEAK_API_KEY, MQTT_*

// ---------------------------------------------------------------------------
// 0. SELECAO DE TRANSPORTE
//
//    Comente USAR_MQTT para voltar ao comportamento da v2 (apenas HTTP).
//    Mantenha USAR_HTTP junto com USAR_MQTT para publicar nos dois e comparar
//    lado a lado no mesmo ciclo -- util durante a coleta de medidas, mas
//    desnecessario em operacao.
// ---------------------------------------------------------------------------
#define USAR_MQTT
#define USAR_HTTP

/*  Formato do topico MQTT.
 *
 *  THINGSPEAK: reaproveita o canal 3493443 ja existente. O ThingSpeak impoe
 *              a estrutura "channels/<id>/publish" e payload em query string,
 *              o que descarta as vantagens de topico hierarquico, LWT e
 *              retain. Serve para nao fragmentar a base historica.
 *
 *  NATIVO:     topicos proprios, payload JSON, LWT e retain disponiveis.
 *              Exige um broker (EMQX publico no ensaio; Mosquitto proprio em
 *              producao).
 *
 *  Definido como NATIVO porque o objetivo do trabalho e exercitar o MQTT, e
 *  nao apenas trocar o meio de transporte mantendo as limitacoes do HTTP.
 */
#define MQTT_NATIVO
// #define MQTT_THINGSPEAK

#ifdef USAR_MQTT
  #include <PubSubClient.h>
  #include <WiFiClientSecure.h>
#endif

// ---------------------------------------------------------------------------
// 1. MAPEAMENTO DE HARDWARE (ESP32-C3)
//    ADC1 do ESP32-C3 cobre GPIO 0 a 4. O ADC2 e inutilizavel com Wi-Fi ativo,
//    por isso os dois sensores analogicos ficam em GPIO 0 e GPIO 1.
// ---------------------------------------------------------------------------
#define DHTPIN        4    // DATA do DHT11 - pino ja validado pela equipe

/* O simulador Wokwi emula o protocolo do DHT22, que NAO e compativel bit a
 * bit com o do DHT11 usado na montagem fisica. Descomente a linha abaixo
 * para rodar no Wokwi; mantenha comentada para gravar na placa real. */
// #define SIMULACAO_WOKWI

#ifdef SIMULACAO_WOKWI
  #define DHTTYPE     DHT22
#else
  #define DHTTYPE     DHT11
#endif

#define PIN_LDR       0    // ADC1_CH0 - fotorresistor
#define PIN_UMIDADE   1    // ADC1_CH1 - sensor capacitivo de umidade
#define PIN_LED       8    // LED de alerta (onboard na maioria das C3)

DHT dht(DHTPIN, DHTTYPE);

// ---------------------------------------------------------------------------
// 2. REGRAS DE NEGOCIO - FAIXAS SEGURAS
//
//    ATENCAO - DIVERGENCIA CONHECIDA ENTRE BORDA E NUVEM.
//    Estes limiares sao de SINALIZACAO LOCAL apenas (o LED). A classificacao
//    de risco com valor de decisao e a do servidor, que conhece qual fruta
//    esta no lote e carrega a faixa com fonte bibliografica:
//
//      uva de mesa ... 0 a 2 C   (Embrapa Semiarido, Lima, 2016)
//      manga ......... 10 a 13 C (USDA Handbook 66; Embrapa, Assis, 2015)
//
//    O valor de 4 C abaixo nao tem fonte: veio do exemplo do enunciado do
//    checkpoint. Mantido nesta versao apenas para nao alterar o comportamento
//    do LED no meio do ensaio comparativo de protocolos. A convergencia com
//    as faixas por fruta e tarefa do proximo ciclo.
// ---------------------------------------------------------------------------
const float TEMP_MAX_SEGURA   = 4.0;    // acima disso: senescencia acelerada
const float TEMP_MIN_SEGURA   = 0.0;    // abaixo disso: dano por congelamento
const float UR_MIN_SEGURA     = 85.0;   // abaixo disso: desidratacao da baga
const float UR_MAX_SEGURA     = 95.0;   // acima disso: condensacao e fungos
const float AGUA_LIVRE_MAX    = 60.0;   // % - agua livre favorece Botrytis
const float LUX_PORTA_ABERTA  = 300.0;  // lux - carga lacrada nao recebe luz

// Limites fisicos do DHT11. Fora disso o sensor esta com defeito.
const float TEMP_LIMITE_MIN = 0.0;
const float TEMP_LIMITE_MAX = 50.0;

// ---------------------------------------------------------------------------
// 3. CODIGOS DE ALERTA (bitmask - alertas sao combinaveis)
// ---------------------------------------------------------------------------
const uint8_t ALERTA_NENHUM        = 0;
const uint8_t ALERTA_TEMP_ALTA     = 1 << 0;  // 1
const uint8_t ALERTA_TEMP_BAIXA    = 1 << 1;  // 2
const uint8_t ALERTA_UR_FORA       = 1 << 2;  // 4
const uint8_t ALERTA_AGUA_LIVRE    = 1 << 3;  // 8
const uint8_t ALERTA_PORTA_ABERTA  = 1 << 4;  // 16

// ---------------------------------------------------------------------------
// 4. TEMPORIZACAO NAO BLOQUEANTE (RNF03)
// ---------------------------------------------------------------------------
const unsigned long INTERVALO_LEITURA = 5000UL;   // amostragem local
const unsigned long INTERVALO_UPDATE  = 20000UL;  // envio (cota ThingSpeak 15s)
const unsigned long INTERVALO_PISCA   = 500UL;    // blink do LED em alerta
const unsigned long INTERVALO_RETRY_MQTT = 5000UL; // espera entre reconexoes

unsigned long ultimaLeitura      = 0;
unsigned long ultimaAtualizacao  = 0;
unsigned long ultimoPisca        = 0;
unsigned long ultimaTentativaMqtt = 0;
bool estadoLed = false;

const char* ID_DISPOSITIVO = "PS-EDGE-01";
const char* ID_LOTE        = "CTR-PNZ-0042";

// ---------------------------------------------------------------------------
// 5. CONFIGURACAO MQTT
// ---------------------------------------------------------------------------
#ifdef USAR_MQTT

/*  Hierarquia de topicos.
 *
 *  O MQTT permite organizar os topicos em arvore, e quem assina pode usar
 *  curingas. O painel pode assinar "plantsync/+/telemetria" para receber a
 *  telemetria de TODOS os nos sem saber de antemao quantos existem, ou
 *  "plantsync/PS-EDGE-01/#" para acompanhar um unico dispositivo.
 *
 *  Isso nao tem equivalente no modelo REST, em que o servidor precisa ser
 *  consultado endpoint a endpoint.
 */
const char* MQTT_TOPICO_BASE = "plantsync";

// Montados em setup(), porque dependem de ID_DISPOSITIVO.
char topicoTelemetria[64];
char topicoStatus[64];
char topicoAlerta[64];

/*  Keep-alive: o no promete falar com o broker ao menos a cada 60 s. Se
 *  silenciar por mais de 1,5x esse intervalo, o broker considera a sessao
 *  morta e publica o Last Will. Como o ciclo de envio e de 20 s, ha folga
 *  confortavel mesmo com uma ou duas falhas seguidas.
 */
const uint16_t MQTT_KEEPALIVE_S = 60;

// Buffer do PubSubClient. O padrao da biblioteca (256 B) nao acomoda o
// payload JSON completo do PlantSync, medido em 255 B mais o topico.
const uint16_t MQTT_BUFFER = 512;

WiFiClientSecure clienteTls;
PubSubClient mqtt(clienteTls);

uint32_t totalPublicacoesMqtt = 0;
uint32_t totalFalhasMqtt      = 0;

/*  Prototipos explicitos.
 *
 *  O pre-processador da Arduino IDE gera prototipos automaticamente, mas os
 *  insere ANTES das diretivas condicionais. Com as funcoes de MQTT dentro de
 *  um #ifdef, isso produz prototipo de funcao inexistente quando USAR_MQTT
 *  esta comentado, e o sketch deixa de compilar. Declarar aqui dentro do
 *  mesmo guarda resolve.
 */
void montarTopicos();
void configurarMqtt();
bool conectarMqtt();
void publicarMqtt(const String &payload);
void aoReceberMqtt(char* topico, byte* payload, unsigned int tamanho);
#endif

#ifdef USAR_HTTP
void enviarHttp();
#endif

// ---------------------------------------------------------------------------
// 6. ESTADO DA AMOSTRA CORRENTE
// ---------------------------------------------------------------------------
struct Telemetria {
  float   temperatura;
  float   umidade;
  float   aguaLivre;
  float   luminosidade;
  long    rssi;
  uint8_t alertas;
  uint8_t risco;     // 0-100
  bool    valida;
};

Telemetria amostra;
uint32_t totalLeituras  = 0;
uint32_t totalDescartes = 0;
uint32_t totalEnviados  = 0;

// ===========================================================================
//  SETUP
// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(2000);  // estabilizacao do monitor serial e do sensor apos energizar

  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  analogReadResolution(12);  // ADC do ESP32-C3: 0..4095

  dht.begin();

  Serial.println();
  Serial.println("================================================");
  Serial.println("   PlantSync - Modulo de Borda v3");
  Serial.print  ("   Dispositivo: "); Serial.println(ID_DISPOSITIVO);
  Serial.print  ("   Lote/Container: "); Serial.println(ID_LOTE);
  Serial.print  ("   Transporte....: ");
#if defined(USAR_MQTT) && defined(USAR_HTTP)
  Serial.println("MQTT + HTTP (modo comparativo)");
#elif defined(USAR_MQTT)
  Serial.println("MQTT");
#else
  Serial.println("HTTP REST");
#endif
  Serial.println("================================================");

  conectarWiFi();

#ifdef USAR_MQTT
  montarTopicos();
  configurarMqtt();
  conectarMqtt();
#endif
}

// ===========================================================================
//  LOOP PRINCIPAL - sem delay(), 100% orientado a millis()
// ===========================================================================
void loop() {
  unsigned long agora = millis();

  // Reconexao automatica de rede (herdado do prototipo original)
  if (WiFi.status() != WL_CONNECTED &&
      agora - ultimaAtualizacao >= INTERVALO_UPDATE) {
    conectarWiFi();
  }

#ifdef USAR_MQTT
  /*  mqtt.loop() precisa rodar a cada iteracao: e ele que processa o PINGRESP
   *  do keep-alive, os PUBACK de QoS 1 e as mensagens recebidas. Sem isso a
   *  sessao cai sozinha depois do keep-alive, mesmo com o Wi-Fi intacto.
   */
  if (mqtt.connected()) {
    mqtt.loop();
  } else if (WiFi.status() == WL_CONNECTED &&
             agora - ultimaTentativaMqtt >= INTERVALO_RETRY_MQTT) {
    ultimaTentativaMqtt = agora;
    conectarMqtt();
  }
#endif

  if (agora - ultimaLeitura >= INTERVALO_LEITURA) {
    ultimaLeitura = agora;
    lerSensores();
  }

  if (agora - ultimaAtualizacao >= INTERVALO_UPDATE) {
    ultimaAtualizacao = agora;
    if (amostra.valida) {
      enviarDadosTelemetria();
    } else {
      // Fail-Fast tambem no MQTT: amostra invalida nao vira publicacao.
      Serial.println("[ENVIO ] Abortado: nenhuma amostra valida (Fail-Fast).");
    }
  }

  atualizarLedAlerta(agora);
}

// ===========================================================================
//  LEITURA + VALIDACAO FAIL-FAST EM DOIS ESTAGIOS (RNF01)
// ===========================================================================
void lerSensores() {
  totalLeituras++;
  amostra.valida = false;

  float temperatura = dht.readTemperature();
  float umidade     = dht.readHumidity();

  // --- Estagio 1: o sensor respondeu? ------------------------------------
  if (isnan(temperatura) || isnan(umidade)) {
    totalDescartes++;
    Serial.println("[FALHA ] DHT11 nao respondeu (NaN). Amostra descartada.");
    return;
  }

  // --- Estagio 2: o valor e fisicamente plausivel? -----------------------
  // Um DHT11 degradado costuma devolver valores dentro do tipo float mas
  // fora da sua propria faixa de operacao. Sem esta barreira, dado invalido
  // entra na nuvem com aparencia de dado bom.
  if (temperatura < TEMP_LIMITE_MIN || temperatura > TEMP_LIMITE_MAX) {
    totalDescartes++;
    Serial.print("[FALHA ] Temperatura fora da faixa do DHT11 (0-50 C): ");
    Serial.println(temperatura);
    return;
  }
  if (umidade < 0.0 || umidade > 100.0) {
    totalDescartes++;
    Serial.print("[FALHA ] Umidade fora de 0-100%: ");
    Serial.println(umidade);
    return;
  }

  // --- Sensores analogicos ------------------------------------------------
  int brutoUmidade = analogRead(PIN_UMIDADE);
  int brutoLuz     = analogRead(PIN_LDR);

  // Sensor capacitivo e invertido: mais agua, menor leitura bruta.
  float aguaLivre = 100.0 - ((float)brutoUmidade / 4095.0 * 100.0);

  // Conversao aproximada do divisor resistivo do LDR para lux.
  // Curva a ser calibrada contra luximetro de referencia.
  float luminosidade = ((float)brutoLuz / 4095.0) * 1000.0;

  amostra.temperatura  = temperatura;
  amostra.umidade      = umidade;
  amostra.aguaLivre    = aguaLivre;
  amostra.luminosidade = luminosidade;
  amostra.rssi         = WiFi.RSSI();
  amostra.alertas      = avaliarAlertas(amostra);
  amostra.risco        = calcularRisco(amostra);
  amostra.valida       = true;

  imprimirLeitura();
}

// ===========================================================================
//  MOTOR DE REGRAS
// ===========================================================================
uint8_t avaliarAlertas(const Telemetria &a) {
  uint8_t flags = ALERTA_NENHUM;

  if (a.temperatura > TEMP_MAX_SEGURA)                    flags |= ALERTA_TEMP_ALTA;
  if (a.temperatura < TEMP_MIN_SEGURA)                    flags |= ALERTA_TEMP_BAIXA;
  if (a.umidade < UR_MIN_SEGURA || a.umidade > UR_MAX_SEGURA) flags |= ALERTA_UR_FORA;
  if (a.aguaLivre > AGUA_LIVRE_MAX)                       flags |= ALERTA_AGUA_LIVRE;
  if (a.luminosidade > LUX_PORTA_ABERTA)                  flags |= ALERTA_PORTA_ABERTA;

  return flags;
}

// Indice sintetico de risco de deterioracao (0 = seguro, 100 = critico).
uint8_t calcularRisco(const Telemetria &a) {
  float risco = 0.0;

  // O desvio termico e o fator dominante na perda pos-colheita.
  if (a.temperatura > TEMP_MAX_SEGURA) {
    risco += (a.temperatura - TEMP_MAX_SEGURA) * 12.0;
  } else if (a.temperatura < TEMP_MIN_SEGURA) {
    risco += (TEMP_MIN_SEGURA - a.temperatura) * 15.0;
  }

  if (a.umidade > UR_MAX_SEGURA)      risco += (a.umidade - UR_MAX_SEGURA) * 3.0;
  else if (a.umidade < UR_MIN_SEGURA) risco += (UR_MIN_SEGURA - a.umidade) * 2.0;

  // Agua livre potencializa qualquer desvio termico (sinergia fungica).
  if (a.aguaLivre > AGUA_LIVRE_MAX)   risco += (a.aguaLivre - AGUA_LIVRE_MAX) * 0.8;

  // Porta aberta em transito: violacao e ganho termico imediato.
  if (a.luminosidade > LUX_PORTA_ABERTA) risco += 20.0;

  if (risco > 100.0) risco = 100.0;
  if (risco < 0.0)   risco = 0.0;
  return (uint8_t)risco;
}

// ===========================================================================
//  SERIALIZACAO JSON (RF01)
//  O MESMO payload alimenta HTTP e MQTT. Isso e o que torna a comparacao
//  valida: a unica variavel entre os dois ensaios e o transporte.
// ===========================================================================
String montarPayloadJson() {
  StaticJsonDocument<384> doc;

  doc["device_id"] = ID_DISPOSITIVO;
  doc["lote_id"]   = ID_LOTE;
  doc["uptime_s"]  = millis() / 1000;
  doc["seq"]       = totalLeituras;

  JsonObject leituras = doc.createNestedObject("leituras");
  leituras["temperatura_c"]    = round(amostra.temperatura * 10) / 10.0;
  leituras["umidade_ar_pct"]   = round(amostra.umidade     * 10) / 10.0;
  leituras["agua_livre_pct"]   = round(amostra.aguaLivre   * 10) / 10.0;
  leituras["luminosidade_lux"] = round(amostra.luminosidade);
  leituras["rssi_dbm"]         = amostra.rssi;

  JsonObject diag = doc.createNestedObject("diagnostico");
  diag["alertas_bitmask"] = amostra.alertas;
  diag["risco_0_100"]     = amostra.risco;
  diag["status"]          = amostra.alertas == ALERTA_NENHUM ? "OK" : "ALERTA";

  String saida;
  serializeJson(doc, saida);
  return saida;
}

// ===========================================================================
//  DESPACHO DE TRANSPORTE
// ===========================================================================
void enviarDadosTelemetria() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ENVIO ] Sem Wi-Fi. Envio adiado para o proximo ciclo.");
    return;
  }

  String payload = montarPayloadJson();
  Serial.println("[JSON  ] Payload serializado:");
  Serial.println(payload);
  Serial.printf("[JSON  ] Tamanho: %u bytes\n", payload.length());

#ifdef USAR_MQTT
  publicarMqtt(payload);
#endif

#ifdef USAR_HTTP
  enviarHttp();
#endif

  Serial.printf("[STATS ] leituras=%u descartadas=%u enviadas=%u",
                totalLeituras, totalDescartes, totalEnviados);
#ifdef USAR_MQTT
  Serial.printf(" | mqtt_ok=%u mqtt_falhas=%u",
                totalPublicacoesMqtt, totalFalhasMqtt);
#endif
  Serial.println();
  Serial.println("------------------------------------------------");
}

// ===========================================================================
//  TRANSPORTE 1 - HTTP REST (comportamento da v2, preservado)
// ===========================================================================
#ifdef USAR_HTTP
void enviarHttp() {
  String url = String("https://api.thingspeak.com/update")
             + "?api_key=" + String(THINGSPEAK_API_KEY)
             + "&field1="  + String(amostra.temperatura, 2)
             + "&field2="  + String(amostra.umidade, 2)
             + "&field3="  + String(amostra.rssi)
             + "&field4="  + String(amostra.aguaLivre, 2)
             + "&field5="  + String(amostra.luminosidade, 0)
             + "&field6="  + String(amostra.alertas)
             + "&field7="  + String(amostra.risco);

  unsigned long t0 = millis();

  HTTPClient http;
  http.setTimeout(8000);
  http.begin(url);   // HTTPS: o core do ESP32 valida a cadeia TLS por padrao
  http.addHeader("User-Agent", "PlantSync-Edge/3.0");

  int httpCode = http.GET();
  unsigned long decorrido = millis() - t0;

  if (httpCode > 0) {
    String resposta = http.getString();
    Serial.printf("[HTTP  ] Codigo %d | entry_id: %s | %lu ms\n",
                  httpCode, resposta.c_str(), decorrido);
    if (httpCode == 200 && resposta != "0") totalEnviados++;
  } else {
    Serial.printf("[HTTP  ] Erro na requisicao: %s | %lu ms\n",
                  http.errorToString(httpCode).c_str(), decorrido);
  }

  http.end();   // fecha a conexao: o proximo envio pagara o handshake de novo
}
#endif

// ===========================================================================
//  TRANSPORTE 2 - MQTT
// ===========================================================================
#ifdef USAR_MQTT

void montarTopicos() {
  snprintf(topicoTelemetria, sizeof(topicoTelemetria),
           "%s/%s/telemetria", MQTT_TOPICO_BASE, ID_DISPOSITIVO);
  snprintf(topicoStatus, sizeof(topicoStatus),
           "%s/%s/status", MQTT_TOPICO_BASE, ID_DISPOSITIVO);
  snprintf(topicoAlerta, sizeof(topicoAlerta),
           "%s/%s/alerta", MQTT_TOPICO_BASE, ID_DISPOSITIVO);

  Serial.println("[MQTT  ] Topicos:");
  Serial.printf("           telemetria -> %s\n", topicoTelemetria);
  Serial.printf("           status ....-> %s\n", topicoStatus);
  Serial.printf("           alerta ....-> %s\n", topicoAlerta);
}

void configurarMqtt() {
  /*  Verificacao TLS.
   *
   *  O ideal e fixar o certificado raiz do broker com clienteTls.setCACert().
   *  O broker publico de ensaio usa cadeia DigiCert; em producao, com broker
   *  proprio, o certificado da equipe entra aqui.
   *
   *  setInsecure() aceita qualquer certificado e esta presente apenas para
   *  o ensaio comparativo. NAO deve ir para operacao: contraria o RNF02.
   */
#ifdef MQTT_CA_CERT
  clienteTls.setCACert(MQTT_CA_CERT);
#else
  clienteTls.setInsecure();   // TODO: fixar a CA antes da entrega final
#endif

  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setKeepAlive(MQTT_KEEPALIVE_S);
  mqtt.setBufferSize(MQTT_BUFFER);
  mqtt.setCallback(aoReceberMqtt);
}

/*  Callback de mensagens recebidas.
 *
 *  Aqui mora uma assimetria importante em relacao ao HTTP: no MQTT o no NAO
 *  precisa perguntar se ha comando para ele. O broker entrega. Isso abre a
 *  porta para reconfigurar o intervalo de envio ou a faixa segura da fruta
 *  em transito, sem firmware novo -- caminho que a v4 deve explorar.
 */
void aoReceberMqtt(char* topico, byte* payload, unsigned int tamanho) {
  Serial.printf("[MQTT  ] Mensagem recebida em %s (%u B): ", topico, tamanho);
  for (unsigned int i = 0; i < tamanho; i++) Serial.print((char)payload[i]);
  Serial.println();
}

bool conectarMqtt() {
  Serial.printf("[MQTT  ] Conectando a %s:%d ... ", MQTT_HOST, MQTT_PORTA);

  /*  Last Will and Testament.
   *
   *  Registrado no momento da conexao. Se o no cair sem enviar DISCONNECT --
   *  queda de energia, travamento, perda de sinal no meio da estrada -- o
   *  broker publica sozinho esta mensagem no topico de status, com retain.
   *
   *  Em cadeia do frio isso resolve um ponto cego real: ate aqui, um
   *  dispositivo que emudecia era indistinguivel de um dispositivo que nao
   *  tinha nada a relatar.
   */
  const char* ultimaVontade = "{\"estado\":\"offline\",\"origem\":\"lwt\"}";

  bool ok;
#ifdef MQTT_USUARIO
  ok = mqtt.connect(ID_DISPOSITIVO, MQTT_USUARIO, MQTT_SENHA,
                    topicoStatus, 1 /* QoS do LWT */, true /* retain */,
                    ultimaVontade);
#else
  ok = mqtt.connect(ID_DISPOSITIVO,
                    topicoStatus, 1, true, ultimaVontade);
#endif

  if (ok) {
    Serial.println("conectado.");

    /*  Anuncio de presenca, tambem com retain. Quem assinar o topico de
     *  status depois recebe imediatamente o estado corrente, sem esperar o
     *  proximo ciclo de 20 s.
     */
    mqtt.publish(topicoStatus, "{\"estado\":\"online\"}", true);

    // Assina o topico de comando deste dispositivo.
    char topicoComando[64];
    snprintf(topicoComando, sizeof(topicoComando),
             "%s/%s/comando", MQTT_TOPICO_BASE, ID_DISPOSITIVO);
    mqtt.subscribe(topicoComando, 1);
    Serial.printf("[MQTT  ] Assinado: %s\n", topicoComando);
  } else {
    totalFalhasMqtt++;
    Serial.printf("falhou (rc=%d). Nova tentativa em %lu s.\n",
                  mqtt.state(), INTERVALO_RETRY_MQTT / 1000);
  }
  return ok;
}

void publicarMqtt(const String &payload) {
  if (!mqtt.connected()) {
    Serial.println("[MQTT  ] Sessao caida. Publicacao adiada.");
    totalFalhasMqtt++;
    return;
  }

  unsigned long t0 = millis();

  /*  PubSubClient publica em QoS 0. A biblioteca nao implementa QoS 1 na
   *  publicacao -- limitacao conhecida e documentada no projeto upstream.
   *  Para QoS 1 e necessario trocar por AsyncMqttClient ou pela pilha
   *  esp-mqtt nativa do ESP-IDF. Registrado como limitacao no relatorio.
   */
  bool ok = mqtt.publish(topicoTelemetria, payload.c_str(), false);
  unsigned long decorrido = millis() - t0;

  if (ok) {
    totalPublicacoesMqtt++;
    totalEnviados++;
    Serial.printf("[MQTT  ] Publicado em %s | %u B | %lu ms\n",
                  topicoTelemetria, payload.length(), decorrido);
  } else {
    totalFalhasMqtt++;
    Serial.printf("[MQTT  ] Falha ao publicar (buffer %u B insuficiente?)\n",
                  MQTT_BUFFER);
  }

  /*  Alerta em topico proprio, com retain.
   *
   *  Separar alerta de telemetria permite que o painel assine so os alertas,
   *  sem processar o fluxo inteiro de leituras. No REST isso exigiria um
   *  endpoint adicional e consulta periodica.
   */
  if (amostra.alertas != ALERTA_NENHUM) {
    StaticJsonDocument<192> doc;
    doc["device_id"] = ID_DISPOSITIVO;
    doc["lote_id"]   = ID_LOTE;
    doc["alertas"]   = amostra.alertas;
    doc["risco"]     = amostra.risco;
    doc["temp_c"]    = round(amostra.temperatura * 10) / 10.0;
    String corpo;
    serializeJson(doc, corpo);
    mqtt.publish(topicoAlerta, corpo.c_str(), true);
    Serial.printf("[MQTT  ] Alerta retido em %s\n", topicoAlerta);
  }
}
#endif  // USAR_MQTT

// ===========================================================================
//  INFRAESTRUTURA
// ===========================================================================
void conectarWiFi() {
  Serial.print("Conectando ao Wi-Fi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {
    delay(500);   // bloqueio tolerado apenas no bootstrap de rede
    Serial.print(".");
    tentativas++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi conectado com sucesso!");
    Serial.print("Endereco IP: ");
    Serial.println(WiFi.localIP());
    Serial.printf("Qualidade do enlace (RSSI): %d dBm\n", WiFi.RSSI());
  } else {
    Serial.println("\nFalha ao conectar. Nova tentativa no proximo ciclo.");
  }
}

void atualizarLedAlerta(unsigned long agora) {
  if (!amostra.valida || amostra.alertas == ALERTA_NENHUM) {
    if (estadoLed) { estadoLed = false; digitalWrite(PIN_LED, LOW); }
    return;
  }
  if (agora - ultimoPisca >= INTERVALO_PISCA) {
    ultimoPisca = agora;
    estadoLed = !estadoLed;
    digitalWrite(PIN_LED, estadoLed ? HIGH : LOW);
  }
}

void imprimirLeitura() {
  Serial.printf("[LEITURA #%u] T=%.1f C | UR=%.1f %% | Agua=%.1f %% | "
                "Luz=%.0f lux | RSSI=%ld dBm | Risco=%u\n",
                totalLeituras, amostra.temperatura, amostra.umidade,
                amostra.aguaLivre, amostra.luminosidade,
                amostra.rssi, amostra.risco);

  if (amostra.alertas == ALERTA_NENHUM) {
    Serial.println("[REGRAS] Carga dentro de todas as faixas seguras.");
    return;
  }
  if (amostra.alertas & ALERTA_TEMP_ALTA)
    Serial.println("[ALERTA] Temperatura acima de 4 C: quebra da cadeia do frio.");
  if (amostra.alertas & ALERTA_TEMP_BAIXA)
    Serial.println("[ALERTA] Temperatura abaixo de 0 C: risco de congelamento.");
  if (amostra.alertas & ALERTA_UR_FORA)
    Serial.println("[ALERTA] Umidade relativa fora da faixa 85-95%.");
  if (amostra.alertas & ALERTA_AGUA_LIVRE)
    Serial.println("[ALERTA] Agua livre acumulada: risco de Botrytis.");
  if (amostra.alertas & ALERTA_PORTA_ABERTA)
    Serial.println("[ALERTA] Luminosidade alta: porta aberta ou violacao.");
}
