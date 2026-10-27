#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 PlantSync - Banco de medicao: HTTPS/REST x MQTT
 Projeto Integrador ADS 4o Periodo - Trabalho III (Aperfeicoamento com MQTT)
-------------------------------------------------------------------------------
 POR QUE ESTE SCRIPT EXISTE

 O enunciado pede comparar MQTT e HTTPS "em termos funcionais e tecnicos".
 Comparacao tecnica sem numero e opiniao. Este script produz os numeros
 medindo o trafego real na rede, nao estimando a partir da especificacao.

 COMO A MEDICAO E FEITA

 Para contar bytes com exatidao, os pacotes MQTT 3.1.1 sao montados byte a
 byte sobre um socket TLS, em vez de delegados a uma biblioteca. Isso permite
 afirmar quantos bytes sairam do dispositivo, e nao quantos deveriam sair.

 A correcao funcional e verificada separadamente, com a biblioteca paho-mqtt:
 um cliente assina um topico, outro publica, e confirma-se o recebimento.
 Medicao sob controle total; corretude validada por biblioteca madura.

 O QUE E MEDIDO

   1. Custo de estabelecimento da sessao (TCP + TLS + handshake do protocolo)
   2. Custo marginal de cada publicacao em regime permanente
   3. Latencia por publicacao
   4. Custo acumulado para uma viagem completa

 Uso:
   python medir_protocolos.py
   python medir_protocolos.py --amostras 20
===============================================================================
"""

import argparse
import json
import os
import socket
import ssl
import struct
import sys
import time
import uuid
from datetime import datetime

# ---------------------------------------------------------------------------
# PARAMETROS DOS ENSAIOS
# ---------------------------------------------------------------------------
# Broker publico de ensaio. Escolhido por apresentar certificado assinado por
# autoridade publicamente confiavel (DigiCert), o que permite manter a
# verificacao TLS estrita exigida pelo RNF02 do projeto.
#
# O test.mosquitto.org tambem foi ensaiado e responde, porem o certificado da
# sua CA propria nao traz a extensao keyUsage, obrigatoria pela RFC 5280 e
# exigida pelo OpenSSL 3 em modo estrito. Usa-lo obrigaria a afrouxar a
# verificacao, o que contrariaria o proprio requisito de seguranca em analise.
BROKER_MQTT = "broker.emqx.io"
PORTA_MQTT_TLS = 8883          # 1883 (sem TLS) esta bloqueado nesta rede
HOST_HTTPS = "api.thingspeak.com"
PORTA_HTTPS = 443

# Chave deliberadamente invalida: o objetivo e medir o custo do protocolo,
# nao gravar no canal real da equipe. A API responde "0" e nao persiste nada,
# mas o tamanho da requisicao na rede e exatamente o de um envio valido.
CHAVE_HTTP_ENSAIO = "CHAVE_DE_ENSAIO_NAO_GRAVA"

PASTA_SAIDA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "evidencias")

def contexto_tls():
    """
    Contexto TLS com verificacao de cadeia e de nome de host ativa.

    Nenhum ensaio deste script desliga a verificacao de certificado: medir
    MQTT com TLS relaxado produziria numeros melhores e conclusao invalida.
    """
    return ssl.create_default_context()


# ===========================================================================
#  SOCKET COM CONTADOR DE BYTES
# ===========================================================================
class SocketContado:
    """
    Envolve um socket e contabiliza cada byte que atravessa a interface.

    A contagem e feita acima da camada TLS: sao os bytes de aplicacao
    entregues ao TLS, nao os bytes cifrados que saem na placa de rede. O
    registro cifrado acrescenta de 22 a 45 bytes por bloco (cabecalho de 5,
    nonce e tag de autenticacao), overhead identico nos dois protocolos e
    que portanto nao altera a comparacao.
    """

    def __init__(self, sock):
        self.sock = sock
        self.enviados = 0
        self.recebidos = 0

    def sendall(self, dados):
        self.enviados += len(dados)
        return self.sock.sendall(dados)

    def recv(self, n):
        dados = self.sock.recv(n)
        self.recebidos += len(dados)
        return dados

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    @property
    def total(self):
        return self.enviados + self.recebidos


# ===========================================================================
#  MONTAGEM DE PACOTES MQTT 3.1.1
#  Referencia: OASIS, MQTT Version 3.1.1, secao 3.
# ===========================================================================
def comprimento_restante(n):
    """
    Codifica o campo "Remaining Length" do cabecalho fixo.

    O MQTT usa inteiro de tamanho variavel: 7 bits de dado por byte e o
    oitavo bit indicando continuacao. Uma mensagem de ate 127 bytes gasta
    um unico byte neste campo. E uma das razoes do cabecalho enxuto.
    """
    saida = bytearray()
    while True:
        digito = n % 128
        n //= 128
        if n > 0:
            digito |= 0x80
        saida.append(digito)
        if n == 0:
            break
    return bytes(saida)


def campo_texto(s):
    """String MQTT: dois bytes de tamanho (big-endian) seguidos do UTF-8."""
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


def pacote_connect(client_id, keepalive=60, usuario=None, senha=None):
    """
    CONNECT - abre a sessao MQTT.

    Pago uma unica vez por sessao. Em regime permanente este custo e
    amortizado por todas as publicacoes seguintes, e e justamente por isso
    que o MQTT se separa do HTTP quando a frequencia de envio sobe.
    """
    corpo = campo_texto("MQTT")          # nome do protocolo
    corpo += bytes([4])                  # nivel 4 = MQTT 3.1.1
    flags = 0x02                         # clean session
    if usuario:
        flags |= 0x80
    if senha:
        flags |= 0x40
    corpo += bytes([flags])
    corpo += struct.pack("!H", keepalive)
    corpo += campo_texto(client_id)
    if usuario:
        corpo += campo_texto(usuario)
    if senha:
        corpo += campo_texto(senha)
    return bytes([0x10]) + comprimento_restante(len(corpo)) + corpo


def pacote_publish(topico, payload, qos=0, id_pacote=None):
    """
    PUBLISH - envia uma mensagem.

    Em QoS 0 o cabecalho resume-se a: 1 byte de tipo e flags, 1 a 4 bytes de
    comprimento e o topico com 2 bytes de tamanho. Nao ha cabecalhos de
    texto, nao ha metodo, nao ha caminho, nao ha User-Agent.
    """
    cabecalho_variavel = campo_texto(topico)
    if qos > 0:
        cabecalho_variavel += struct.pack("!H", id_pacote)
    corpo = cabecalho_variavel + payload.encode("utf-8")
    tipo_flags = 0x30 | (qos << 1)
    return bytes([tipo_flags]) + comprimento_restante(len(corpo)) + corpo


def pacote_disconnect():
    return bytes([0xE0, 0x00])


def ler_pacote(sock, timeout=10):
    """Le um pacote MQTT completo, respeitando o comprimento variavel."""
    sock.sock.settimeout(timeout)
    cabecalho = sock.recv(1)
    if not cabecalho:
        return None, b""
    tipo = cabecalho[0]
    comprimento = 0
    multiplicador = 1
    while True:
        b = sock.recv(1)
        if not b:
            return tipo, b""
        comprimento += (b[0] & 127) * multiplicador
        if not (b[0] & 0x80):
            break
        multiplicador *= 128
    corpo = b""
    while len(corpo) < comprimento:
        pedaco = sock.recv(comprimento - len(corpo))
        if not pedaco:
            break
        corpo += pedaco
    return tipo, corpo


# ===========================================================================
#  PAYLOAD DE ENSAIO
#  Reproduz exatamente o que o firmware v2 serializa.
# ===========================================================================
def montar_payload(seq):
    doc = {
        "device_id": "PS-EDGE-01",
        "lote_id": "CTR-PNZ-0042",
        "uptime_s": 1200 + seq * 20,
        "seq": seq,
        "leituras": {
            "temperatura_c": 1.8,
            "umidade_ar_pct": 90.4,
            "agua_livre_pct": 41.7,
            "luminosidade_lux": 5,
            "rssi_dbm": -58,
        },
        "diagnostico": {
            "alertas_bitmask": 0,
            "risco_0_100": 0,
            "status": "OK",
        },
    }
    return json.dumps(doc, separators=(",", ":"))


# ===========================================================================
#  ENSAIO 1 - MQTT SOBRE TLS
# ===========================================================================
def ensaio_mqtt(amostras, qos=0):
    topico = f"plantsync/ensaio/{uuid.uuid4().hex[:8]}/telemetria"
    client_id = f"ps-edge-{uuid.uuid4().hex[:8]}"

    resultado = {
        "protocolo": f"MQTT 3.1.1 sobre TLS (QoS {qos})",
        "broker": f"{BROKER_MQTT}:{PORTA_MQTT_TLS}",
        "topico": topico,
        "amostras": amostras,
        "qos": qos,
    }

    contexto = contexto_tls()

    # --- Estabelecimento da sessao ---------------------------------------
    t0 = time.perf_counter()
    bruto = socket.create_connection((BROKER_MQTT, PORTA_MQTT_TLS), timeout=15)
    t_tcp = time.perf_counter()
    tls = contexto.wrap_socket(bruto, server_hostname=BROKER_MQTT)
    t_tls = time.perf_counter()

    sock = SocketContado(tls)
    sock.sendall(pacote_connect(client_id))
    tipo, _ = ler_pacote(sock)
    t_conn = time.perf_counter()

    if tipo is None or (tipo & 0xF0) != 0x20:
        sock.close()
        raise RuntimeError(f"CONNACK nao recebido (tipo={tipo})")

    resultado["ms_tcp"] = round((t_tcp - t0) * 1000, 1)
    resultado["ms_tls"] = round((t_tls - t_tcp) * 1000, 1)
    resultado["ms_handshake_protocolo"] = round((t_conn - t_tls) * 1000, 1)
    resultado["ms_sessao_total"] = round((t_conn - t0) * 1000, 1)
    resultado["bytes_sessao"] = sock.total

    # --- Regime permanente ------------------------------------------------
    bytes_antes = sock.total
    latencias = []
    tamanhos_payload = []

    for i in range(1, amostras + 1):
        payload = montar_payload(i)
        tamanhos_payload.append(len(payload.encode("utf-8")))
        pkt = pacote_publish(topico, payload, qos=qos, id_pacote=i)

        t_pub = time.perf_counter()
        sock.sendall(pkt)
        if qos == 1:
            # Em QoS 1 o broker confirma com PUBACK: ha garantia de entrega,
            # ao custo de uma volta adicional na rede.
            tipo_ack, _ = ler_pacote(sock)
            if tipo_ack is None or (tipo_ack & 0xF0) != 0x40:
                raise RuntimeError("PUBACK nao recebido")
        latencias.append((time.perf_counter() - t_pub) * 1000)

    bytes_publicacoes = sock.total - bytes_antes

    sock.sendall(pacote_disconnect())
    sock.close()

    resultado["bytes_publicacoes"] = bytes_publicacoes
    resultado["bytes_por_publicacao"] = round(bytes_publicacoes / amostras, 1)
    resultado["bytes_payload_medio"] = round(sum(tamanhos_payload) / amostras, 1)
    resultado["bytes_overhead_por_publicacao"] = round(
        (bytes_publicacoes / amostras) - (sum(tamanhos_payload) / amostras), 1)
    resultado["ms_latencia_media"] = round(sum(latencias) / len(latencias), 2)
    resultado["ms_latencia_min"] = round(min(latencias), 2)
    resultado["ms_latencia_max"] = round(max(latencias), 2)
    resultado["bytes_total"] = resultado["bytes_sessao"] + bytes_publicacoes

    return resultado


# ===========================================================================
#  ENSAIO 2 - HTTPS/REST
# ===========================================================================
def ensaio_https(amostras):
    """
    Cada envio HTTP abre uma conexao nova, exatamente como faz o firmware
    atual: HTTPClient.begin() ... http.GET() ... http.end(). E o pior caso
    realista do REST em dispositivo embarcado, e e o que esta em producao.
    """
    resultado = {
        "protocolo": "HTTP/1.1 sobre TLS (REST, conexao por envio)",
        "host": f"{HOST_HTTPS}:{PORTA_HTTPS}",
        "amostras": amostras,
    }

    contexto = contexto_tls()
    total_bytes = 0
    latencias = []
    bytes_primeira_sessao = None
    tamanhos_requisicao = []

    for i in range(1, amostras + 1):
        query = (f"/update?api_key={CHAVE_HTTP_ENSAIO}"
                 f"&field1=1.80&field2=90.40&field3=-58"
                 f"&field4=41.70&field5=5&field6=0&field7=0")
        requisicao = (
            f"GET {query} HTTP/1.1\r\n"
            f"Host: {HOST_HTTPS}\r\n"
            f"User-Agent: PlantSync-Edge/2.0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        tamanhos_requisicao.append(len(requisicao.encode("utf-8")))

        t0 = time.perf_counter()
        bruto = socket.create_connection((HOST_HTTPS, PORTA_HTTPS), timeout=15)
        tls = contexto.wrap_socket(bruto, server_hostname=HOST_HTTPS)
        sock = SocketContado(tls)

        sock.sendall(requisicao.encode("utf-8"))
        resposta = b""
        sock.sock.settimeout(15)
        while True:
            try:
                pedaco = sock.recv(4096)
            except (socket.timeout, ssl.SSLError):
                break
            if not pedaco:
                break
            resposta += pedaco
        latencias.append((time.perf_counter() - t0) * 1000)
        sock.close()

        if bytes_primeira_sessao is None:
            bytes_primeira_sessao = sock.total
            resultado["amostra_resposta"] = resposta.split(b"\r\n\r\n")[-1][:40].decode(
                "utf-8", "replace").strip()
            cabecalhos = resposta.split(b"\r\n\r\n")[0]
            resultado["bytes_cabecalho_resposta"] = len(cabecalhos)
            resultado["linha_status"] = cabecalhos.split(b"\r\n")[0].decode(
                "utf-8", "replace")

        total_bytes += sock.total

    resultado["bytes_total"] = total_bytes
    resultado["bytes_por_publicacao"] = round(total_bytes / amostras, 1)
    resultado["bytes_requisicao_media"] = round(
        sum(tamanhos_requisicao) / amostras, 1)
    resultado["bytes_overhead_por_publicacao"] = round(
        total_bytes / amostras - sum(tamanhos_requisicao) / amostras, 1)
    resultado["ms_latencia_media"] = round(sum(latencias) / len(latencias), 2)
    resultado["ms_latencia_min"] = round(min(latencias), 2)
    resultado["ms_latencia_max"] = round(max(latencias), 2)

    return resultado


# ===========================================================================
#  ENSAIO 3 - CORRETUDE FUNCIONAL (paho-mqtt)
#  Prova que a mensagem publicada chega a quem assinou o topico.
# ===========================================================================
def ensaio_funcional():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return {"erro": "paho-mqtt nao instalado"}

    topico = f"plantsync/ensaio/{uuid.uuid4().hex[:8]}/telemetria"
    recebidas = []
    pronto = {"assinado": False}

    def ao_conectar(cliente, dados, flags, rc, props=None):
        cliente.subscribe(topico, qos=1)

    def ao_assinar(cliente, dados, mid, qos, props=None):
        pronto["assinado"] = True

    def ao_receber(cliente, dados, msg):
        recebidas.append({
            "topico": msg.topic,
            "qos": msg.qos,
            "bytes": len(msg.payload),
            "conteudo": json.loads(msg.payload.decode("utf-8")),
        })

    try:
        assinante = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                client_id=f"ps-sub-{uuid.uuid4().hex[:6]}")
    except AttributeError:
        assinante = mqtt.Client(client_id=f"ps-sub-{uuid.uuid4().hex[:6]}")

    assinante.on_connect = ao_conectar
    assinante.on_subscribe = ao_assinar
    assinante.on_message = ao_receber
    assinante.tls_set()
    assinante.connect(BROKER_MQTT, PORTA_MQTT_TLS, 60)
    assinante.loop_start()

    limite = time.time() + 15
    while not pronto["assinado"] and time.time() < limite:
        time.sleep(0.1)
    if not pronto["assinado"]:
        assinante.loop_stop()
        return {"erro": "assinatura do topico nao confirmada"}

    try:
        publicador = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                 client_id=f"ps-pub-{uuid.uuid4().hex[:6]}")
    except AttributeError:
        publicador = mqtt.Client(client_id=f"ps-pub-{uuid.uuid4().hex[:6]}")

    publicador.tls_set()
    publicador.connect(BROKER_MQTT, PORTA_MQTT_TLS, 60)
    publicador.loop_start()

    payload = montar_payload(99)
    info = publicador.publish(topico, payload, qos=1)
    info.wait_for_publish(timeout=10)

    limite = time.time() + 15
    while not recebidas and time.time() < limite:
        time.sleep(0.1)

    publicador.loop_stop()
    publicador.disconnect()
    assinante.loop_stop()
    assinante.disconnect()

    return {
        "topico": topico,
        "publicado_bytes": len(payload.encode("utf-8")),
        "entregue": len(recebidas) > 0,
        "mensagens_recebidas": recebidas,
    }


# ===========================================================================
#  RELATORIO
# ===========================================================================
def emitir(resultados):
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    linhas = []
    add = linhas.append

    add("=" * 78)
    add(" PLANTSYNC - MEDICAO COMPARATIVA: HTTPS/REST x MQTT")
    add(" Projeto Integrador ADS 4o Periodo")
    add(f" Executado em: {datetime.now():%d/%m/%Y %H:%M:%S}")
    add(f" Python {sys.version.split()[0]} | {sys.platform}")
    add("=" * 78)
    add("")
    add("NOTA SOBRE A CONTAGEM DE BYTES")
    add("-" * 78)
    add("  Os bytes contabilizados sao os de aplicacao entregues ao TLS, nao os")
    add("  bytes cifrados na interface de rede. O registro TLS acrescenta de 22 a")
    add("  45 bytes por bloco, overhead presente nos dois protocolos e que nao")
    add("  altera a comparacao relativa.")
    add("")
    add("NOTA SOBRE AS LATENCIAS - LEITURA OBRIGATORIA")
    add("-" * 78)
    add("  As tres latencias medidas NAO sao grandezas equivalentes e nao devem")
    add("  ser comparadas diretamente:")
    add("")
    add("  MQTT QoS 0  mede apenas o tempo de entregar os bytes ao buffer TLS.")
    add("              Nao ha confirmacao do broker: o protocolo e deliberadamente")
    add("              do tipo 'dispare e esqueca'. O valor na casa dos")
    add("              centesimos de milissegundo e custo local de CPU, NAO prova")
    add("              de entrega. Concluir dai que o MQTT e milhares de vezes")
    add("              mais rapido seria erro de interpretacao.")
    add("")
    add("  MQTT QoS 1  mede a volta completa ate o PUBACK do broker. Este sim e")
    add("              tempo de confirmacao de entrega, comparavel ao do HTTP.")
    add("")
    add("  HTTPS       mede a operacao inteira: conexao TCP, handshake TLS,")
    add("              requisicao e resposta. O firmware atual abre e fecha a")
    add("              conexao a cada envio, portanto este e o custo real em")
    add("              producao, nao um pior caso artificial.")
    add("")
    add("  A comparacao honesta de latencia e MQTT QoS 1 contra HTTPS.")
    add("")

    for r in resultados:
        if "erro" in r:
            add(f"ENSAIO COM FALHA: {r['erro']}")
            add("")
            continue

        if "protocolo" in r:
            add("=" * 78)
            add(f" {r['protocolo']}")
            add("=" * 78)
            destino = r.get("broker") or r.get("host")
            add(f"  Destino ............................: {destino}")
            if "topico" in r:
                add(f"  Topico .............................: {r['topico']}")
            add(f"  Amostras ...........................: {r['amostras']}")
            add("")

            if "ms_sessao_total" in r:
                add("  ESTABELECIMENTO DA SESSAO (uma vez por conexao)")
                add(f"    Conexao TCP ......................: {r['ms_tcp']:>8.1f} ms")
                add(f"    Handshake TLS ....................: {r['ms_tls']:>8.1f} ms")
                add(f"    CONNECT/CONNACK MQTT .............: {r['ms_handshake_protocolo']:>8.1f} ms")
                add(f"    Total da sessao ..................: {r['ms_sessao_total']:>8.1f} ms")
                add(f"    Bytes do handshake MQTT ..........: {r['bytes_sessao']:>8} B")
                add("")

            if "linha_status" in r:
                add(f"  Resposta do servidor ...............: {r['linha_status']}")
                add(f"  Corpo da resposta ..................: \"{r['amostra_resposta']}\"")
                add(f"  Cabecalhos da resposta .............: {r['bytes_cabecalho_resposta']} B")
                add("")

            add("  REGIME PERMANENTE (por publicacao)")
            add(f"    Bytes totais .....................: {r['bytes_por_publicacao']:>8.1f} B")
            base = r.get("bytes_payload_medio") or r.get("bytes_requisicao_media")
            rotulo = "Payload util" if "bytes_payload_medio" in r else "Requisicao"
            add(f"    {rotulo:<32}..: {base:>8.1f} B")
            add(f"    Overhead de protocolo ............: {r['bytes_overhead_por_publicacao']:>8.1f} B")
            add(f"    Latencia media ...................: {r['ms_latencia_media']:>8.2f} ms")
            add(f"    Latencia min / max ...............: {r['ms_latencia_min']:.2f} / {r['ms_latencia_max']:.2f} ms")
            add("")
            add(f"  TOTAL DO ENSAIO ....................: {r['bytes_total']} B")
            add("")

        elif "entregue" in r:
            add("=" * 78)
            add(" ENSAIO FUNCIONAL - ENTREGA FIM A FIM (paho-mqtt)")
            add("=" * 78)
            add(f"  Topico .............................: {r['topico']}")
            add(f"  Payload publicado ..................: {r['publicado_bytes']} B")
            add(f"  Entregue ao assinante ..............: {'SIM' if r['entregue'] else 'NAO'}")
            for m in r["mensagens_recebidas"]:
                add(f"    Recebido em ....................: {m['topico']}")
                add(f"    QoS efetivo ....................: {m['qos']}")
                add(f"    Bytes ..........................: {m['bytes']}")
                add(f"    device_id ......................: {m['conteudo']['device_id']}")
                add(f"    temperatura_c ..................: {m['conteudo']['leituras']['temperatura_c']}")
                add(f"    status .........................: {m['conteudo']['diagnostico']['status']}")
            add("")

    # --- Consolidacao ------------------------------------------------------
    mqtt0 = next((r for r in resultados if r.get("qos") == 0), None)
    http = next((r for r in resultados if "host" in r), None)

    if mqtt0 and http:
        add("=" * 78)
        add(" CONSOLIDACAO")
        add("=" * 78)
        razao = http["bytes_por_publicacao"] / mqtt0["bytes_por_publicacao"]
        economia = 100 * (1 - mqtt0["bytes_por_publicacao"] / http["bytes_por_publicacao"])
        add(f"  Bytes por publicacao - HTTPS .......: {http['bytes_por_publicacao']:>8.1f} B")
        add(f"  Bytes por publicacao - MQTT QoS 0 ..: {mqtt0['bytes_por_publicacao']:>8.1f} B")
        add(f"  Razao HTTPS / MQTT .................: {razao:>8.1f} x")
        add(f"  Economia do MQTT ...................: {economia:>8.1f} %")
        add("")

        # Projecao para uma viagem real
        for horas, rotulo in [(72, "Viagem Petrolina-Pecem (72 h)")]:
            envios = int(horas * 3600 / 20)   # um envio a cada 20 s
            b_http = envios * http["bytes_por_publicacao"]
            b_mqtt = mqtt0["bytes_sessao"] + envios * mqtt0["bytes_por_publicacao"]
            add(f"  {rotulo} - {envios} envios a cada 20 s")
            add(f"    HTTPS ............................: {b_http/1024:>8.1f} KiB")
            add(f"    MQTT (1 sessao + N publicacoes) ..: {b_mqtt/1024:>8.1f} KiB")
            add(f"    Diferenca ........................: {(b_http-b_mqtt)/1024:>8.1f} KiB "
                f"({100*(1-b_mqtt/b_http):.1f} % menos)")
            add("")

    add("=" * 78)
    texto = "\n".join(linhas)
    print(texto)

    caminho = os.path.join(PASTA_SAIDA, "mqtt-medicao.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    print(f"\n[SAIDA] {caminho}")

    caminho_json = os.path.join(PASTA_SAIDA, "mqtt-medicao.json")
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"[SAIDA] {caminho_json}")


def main():
    ap = argparse.ArgumentParser(
        description="Mede o custo real de HTTPS/REST e MQTT para o PlantSync.")
    ap.add_argument("--amostras", type=int, default=10)
    args = ap.parse_args()

    resultados = []

    print(f"[1/4] MQTT QoS 0 sobre TLS ({args.amostras} publicacoes)...")
    try:
        resultados.append(ensaio_mqtt(args.amostras, qos=0))
    except Exception as e:
        resultados.append({"erro": f"MQTT QoS 0: {type(e).__name__}: {e}"})

    print(f"[2/4] MQTT QoS 1 sobre TLS ({args.amostras} publicacoes)...")
    try:
        resultados.append(ensaio_mqtt(args.amostras, qos=1))
    except Exception as e:
        resultados.append({"erro": f"MQTT QoS 1: {type(e).__name__}: {e}"})

    print(f"[3/4] HTTPS/REST ({args.amostras} requisicoes)...")
    try:
        resultados.append(ensaio_https(args.amostras))
    except Exception as e:
        resultados.append({"erro": f"HTTPS: {type(e).__name__}: {e}"})

    print("[4/4] Ensaio funcional de entrega (paho-mqtt)...")
    try:
        resultados.append(ensaio_funcional())
    except Exception as e:
        resultados.append({"erro": f"Funcional: {type(e).__name__}: {e}"})

    print()
    emitir(resultados)


if __name__ == "__main__":
    main()
