"""Servidor local leve para testar o frontend e a API sem instalar dependências."""

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from apuracao_presidente.application.web_snapshot import (  # noqa: E402
    collect_web_snapshot,
    project_web_snapshot,
)


class DevelopmentHandler(SimpleHTTPRequestHandler):
    mock = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT / "public"), **kwargs)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/snapshot":
            if parsed.path == "/":
                self.path = "/index.html"
            super().do_GET()
            return
        query = parse_qs(parsed.query)
        if query.get("health") == ["1"]:
            self._json(200, {"status": "ok", "service": "apuracao-presidente"})
            return
        collection = collect_web_snapshot(mock=self.mock or query.get("mock") == ["1"])
        self._json(200 if collection["status"] == "completo" else 502, {"coleta": collection})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/snapshot":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length))
            result = project_web_snapshot(payload["coleta"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._json(400, {"erro": str(error)})
            return
        self._json(200, {"resultado": result})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    DevelopmentHandler.mock = args.mock
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DevelopmentHandler)
    suffix = "?mock=1" if args.mock else ""
    print(f"Aplicação disponível em http://127.0.0.1:{args.port}/{suffix}")
    server.serve_forever()


if __name__ == "__main__":
    main()
