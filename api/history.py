"""Consulta pública do histórico compacto salvo pelo diário."""

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from apuracao_presidente.application.journal import list_journal_history  # noqa: E402
from apuracao_presidente.infrastructure.journal_storage import journal_storage  # noqa: E402


LOGGER = logging.getLogger("apuracao_presidente.history")
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

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        try:
            raw_limit = int(query.get("limite", ["360"])[0])
            limit = min(max(raw_limit, 1), 1440)
            history = list_journal_history(
                journal_storage(PROJECT_ROOT),
                date=query.get("data", [None])[0],
                mock=query.get("mock") == ["1"],
                limit=limit,
            )
        except (ValueError, TypeError) as error:
            self._send_json(400, {"erro": str(error)})
            return
        except Exception as error:  # noqa: BLE001 - fronteira HTTP de leitura
            LOGGER.exception("Falha ao consultar o diário")
            self._send_json(500, {"erro": f"{type(error).__name__}: {error}"})
            return
        schedule_active = os.environ.get("DIARY_MINUTE_SCHEDULE_ACTIVE") == "1"
        self._send_json(
            200,
            {
                "historico": history,
                "agendamento": {
                    "ativo": schedule_active,
                    "intervalo_minutos": 1,
                    "estado": "automatico" if schedule_active else "aguardando_vercel_pro",
                },
            },
        )
