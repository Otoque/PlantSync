"""Serve a página pública do PlantSync somente na rede local."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

FRONT = Path(__file__).resolve().parent.parent / "front_end"
API = "http://127.0.0.1:8000"
ARQUIVOS = {
    "/publico.html": ("publico.html", "text/html; charset=utf-8"),
    "/css/externas.css": ("css/externas.css", "text/css; charset=utf-8"),
    "/js/externas.js": ("js/externas.js", "text/javascript; charset=utf-8"),
    "/js/dados.js": ("js/dados.js", "text/javascript; charset=utf-8"),
    "/js/mapa-publico.js": ("js/mapa-publico.js", "text/javascript; charset=utf-8"),
    "/vendor/leaflet/leaflet.css": ("vendor/leaflet/leaflet.css", "text/css; charset=utf-8"),
    "/vendor/leaflet/leaflet.js": ("vendor/leaflet/leaflet.js", "text/javascript; charset=utf-8"),
    "/mapas/nordeste.geojson": ("mapas/nordeste.geojson", "application/geo+json"),
}
CODIGO = re.compile(r"/api/publico/[A-Za-z0-9_-]{8}")
TRAJETO = re.compile(r"/mapas/publicos/[A-Za-z0-9_-]{8}\.json")
POLITICA = "default-src 'self'; base-uri 'none'; object-src 'none'; form-action 'none'; frame-ancestors 'none'"
REDES_PRIVADAS = tuple(map(IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))
ARQUIVOS_DE_TRAJETO = FRONT / "mapas" / "publicos"
CAMPOS_PUBLICOS = ("fruta", "produtor", "origem", "selo_faixa_segura")


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


cliente = build_opener(ProxyHandler({}), SemRedirecionamento())


class PaginaPublica(BaseHTTPRequestHandler):
    timeout = 8

    def log_message(self, *args):
        pass

    def responder(self, status, tipo, corpo):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", POLITICA)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if IPv4Address(self.client_address[0]) not in self.server.subrede:
            self.responder(403, "text/plain", b"Disponivel somente na rede local.")
            return

        caminho = self.path.partition("?")[0]
        if caminho in ARQUIVOS:
            arquivo, tipo = ARQUIVOS[caminho]
            self.responder(200, tipo, (FRONT / arquivo).read_bytes())
        elif TRAJETO.fullmatch(caminho):
            arquivo = (FRONT / caminho.lstrip("/")).resolve()
            if arquivo.parent == ARQUIVOS_DE_TRAJETO and arquivo.is_file():
                self.responder(200, "application/json; charset=utf-8", arquivo.read_bytes())
            else:
                self.responder(404, "text/plain", b"Trajeto nao encontrado.")
        elif CODIGO.fullmatch(caminho):
            try:
                with cliente.open(API + caminho, timeout=5) as resposta:
                    corpo = resposta.read(8193)
                if len(corpo) > 8192:
                    self.responder(502, "application/json", b'{"erro":"Resposta indisponivel."}')
                    return
                registro = json.loads(corpo)
                publico = {campo: registro[campo] for campo in CAMPOS_PUBLICOS}
                self.responder(200, "application/json; charset=utf-8", json.dumps(publico).encode())
            except HTTPError as erro:
                if erro.code == 404:
                    self.responder(404, "application/json", b'{"erro":"Lote nao encontrado."}')
                else:
                    self.responder(502, "application/json", b'{"erro":"API indisponivel."}')
            except (URLError, TimeoutError, ValueError, KeyError, TypeError):
                self.responder(502, "application/json", b'{"erro":"API indisponivel."}')
        else:
            self.responder(404, "text/plain", b"Pagina nao encontrada.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python tools/servir_qr_local.py 192.168.1.20/24")
    interface = IPv4Interface(sys.argv[1])
    if not any(interface.network.subnet_of(rede) for rede in REDES_PRIVADAS):
        raise SystemExit("Informe um IPv4 privado da interface local com o prefixo da rede.")
    with ThreadingHTTPServer((str(interface.ip), 5501), PaginaPublica) as servidor:
        servidor.subrede = interface.network
        print(f"Página pública disponível em http://{interface.ip}:5501", flush=True)
        servidor.serve_forever()
