"""Serve o painel de desenvolvimento somente em loopback."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


FRONT = Path(__file__).resolve().parent.parent / "front_end"


class PainelLocal(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONT), **kwargs)

    def end_headers(self):
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        super().end_headers()


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 5500), PainelLocal) as servidor:
        print("Painel local disponível em http://127.0.0.1:5500", flush=True)
        servidor.serve_forever()
