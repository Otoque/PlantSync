/*
 * ============================================================================
 *  PlantSync - Modulo de Borda v2
 *  Telemetria de microclima para frutas de exportacao do Vale do Sao Francisco
 *  Projeto Integrador - ADS 4o Periodo
 * ----------------------------------------------------------------------------
 *  EVOLUCAO DO PROTOTIPO DE 16/09.
 *  Mantem o hardware validado pela equipe (ESP32-C3 + DHT11 no GPIO 4) e a
 *  estrutura de funcoes do main.ino original. Acrescenta:
 *
 *    - Sensor de umidade capacitivo ... agua livre / condensacao no piso
 *    - LDR / fotorresistor ........... luminosidade = deteccao de porta aberta
 *    - LED de alerta local ........... sinalizacao independente da nuvem
 *    - Motor de regras de negocio .... faixas seguras da cadeia do frio
 *    - Validacao Fail-Fast em 2 estagios
 *    - Payload JSON estruturado (ArduinoJson) alem da query string ThingSpeak
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
 *    RNF01 - Fail-Fast  : leitura invalida aborta o envio, nao polui a nuvem.
 *    RNF02 - Seguranca  : credenciais em credentials.h, fora do versionamento.
 *    RNF03 - Desempenho : temporizacao nao bloqueante com millis().
 * ============================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "DHT.h"
#include "credentials.h"  // WIFI_SSID, WIFI_PASSWORD, THINGSPEAK_API_KEY

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
//    Calibrado para uva de mesa refrigerada. Os limiares devem ser
//    revalidados com o produtor parceiro antes da entrega final.
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

unsigned long ultimaLeitura      = 0;
unsigned long ultimaAtualizacao  = 0;
unsigned long ultimoPisca        = 0;
bool estadoLed = false;

// ---------------------------------------------------------------------------
// 5. ESTADO DA AMOSTRA CORRENTE
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

const char* ID_DISPOSITIVO = "PS-EDGE-01";
const char* ID_LOTE        = "CTR-PNZ-0042";

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
  Serial.println("   PlantSync - Modulo de Borda v2");
  Serial.print  ("   Dispositivo: "); Serial.println(ID_DISPOSITIVO);
  Serial.print  ("   Lote/Container: "); Serial.println(ID_LOTE);
  Serial.println("================================================");

  conectarWiFi();
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

  if (agora - ultimaLeitura >= INTERVALO_LEITURA) {
    ultimaLeitura = agora;
    lerSensores();
  }

  if (agora - ultimaAtualizacao >= INTERVALO_UPDATE) {
    ultimaAtualizacao = agora;
    if (amostra.valida) {
      enviarDadosTelemetria();
    } else {
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
//  ENVIO REST
// ===========================================================================
void enviarDadosTelemetria() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ENVIO ] Sem Wi-Fi. Envio adiado para o proximo ciclo.");
    return;
  }

  Serial.println("[JSON  ] Payload serializado:");
  Serial.println(montarPayloadJson());

  String url = String("https://api.thingspeak.com/update")
             + "?api_key=" + String(THINGSPEAK_API_KEY)
             + "&field1="  + String(amostra.temperatura, 2)
             + "&field2="  + String(amostra.umidade, 2)
             + "&field3="  + String(amostra.rssi)
             + "&field4="  + String(amostra.aguaLivre, 2)
             + "&field5="  + String(amostra.luminosidade, 0)
             + "&field6="  + String(amostra.alertas)
             + "&field7="  + String(amostra.risco);

  HTTPClient http;
  http.setTimeout(8000);
  http.begin(url);   // HTTPS: o core do ESP32 valida a cadeia TLS por padrao
  http.addHeader("User-Agent", "PlantSync-Edge/2.0");

  int httpCode = http.GET();

  if (httpCode > 0) {
    String resposta = http.getString();
    Serial.printf("[HTTP  ] Codigo %d | entry_id: %s\n",
                  httpCode, resposta.c_str());
    if (httpCode == 200 && resposta != "0") totalEnviados++;
  } else {
    Serial.printf("[HTTP  ] Erro na requisicao: %s\n",
                  http.errorToString(httpCode).c_str());
  }

  http.end();

  Serial.printf("[STATS ] leituras=%u descartadas=%u enviadas=%u\n",
                totalLeituras, totalDescartes, totalEnviados);
  Serial.println("------------------------------------------------");
}

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
