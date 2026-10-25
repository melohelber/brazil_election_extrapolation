"""Vercel Cron: coleta, projeta e arquiva uma rodada por minuto."""

from http.server import BaseHTTPRequestHandler
import hmac
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from apuracao_presidente.application.journal import run_journal_entry  # noqa: E402
from apuracao_presidente.infrastructure.journal_storage import journal_storage  # noqa: E402


LOGGER = logging.getLogger("apuracao_presidente.cron")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        secret = os.environ.get("CRON_SECRET")
        authorization = self.headers.get("Authorization", "")
        return bool(secret) and hmac.compare_digest(authorization, f"Bearer {secret}")

    def do_GET(self) -> None:
        if not self._authorized():
            LOGGER.warning("Execução do diário rejeitada por autenticação")
            self._send_json(401, {"erro": "Não autorizado"})
            return
        try:
            summary = run_journal_entry(journal_storage(PROJECT_ROOT), logger=LOGGER)
        except Exception as error:  # noqa: BLE001 - fronteira HTTP do cron
            LOGGER.exception("Falha na execução automática do diário")
            self._send_json(500, {"erro": f"{type(error).__name__}: {error}"})
            return
        self._send_json(200, {"status": "ok", "rodada": summary})
