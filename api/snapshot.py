"""Vercel Function para coleta e projeção da apuração."""

from http.server import BaseHTTPRequestHandler
import json
import logging
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from apuracao_presidente.application.web_snapshot import (  # noqa: E402
    collect_web_snapshot,
    project_web_snapshot,
)
from apuracao_presidente.application.journal import save_journal_entry  # noqa: E402
from apuracao_presidente.infrastructure.journal_storage import journal_storage  # noqa: E402


LOGGER = logging.getLogger("apuracao_presidente.api")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)


class handler(BaseHTTPRequestHandler):
    """Adaptador HTTP sem dependências externas para o runtime Python do Vercel."""

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
        if query.get("health") == ["1"]:
            self._send_json(200, {"status": "ok", "service": "apuracao-presidente"})
            return

        mock = query.get("mock") == ["1"]
        try:
            collection = collect_web_snapshot(mock=mock, logger=LOGGER)
        except Exception as error:  # noqa: BLE001 - limite HTTP do adaptador
            LOGGER.exception("Falha geral na coleta web")
            self._send_json(500, {"erro": f"{type(error).__name__}: {error}"})
            return

        status = 200 if collection["status"] == "completo" else 502
        self._send_json(status, {"coleta": collection})

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 4_000_000:
                raise ValueError("Corpo da requisição ausente ou grande demais")
            payload = json.loads(self.rfile.read(content_length))
            collection = payload.get("coleta")
            if not isinstance(collection, dict):
                raise ValueError("Campo 'coleta' ausente ou inválido")
            result = project_web_snapshot(collection)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            LOGGER.warning("Projeção rejeitada: %s", error)
            self._send_json(400, {"erro": str(error)})
            return
        except Exception as error:  # noqa: BLE001 - limite HTTP do adaptador
            LOGGER.exception("Falha geral na projeção web")
            self._send_json(500, {"erro": f"{type(error).__name__}: {error}"})
            return

        journal: dict[str, Any]
        try:
            journal = {
                "salvo": True,
                "rodada": save_journal_entry(
                    collection,
                    result,
                    journal_storage(PROJECT_ROOT),
                    logger=LOGGER,
                ),
            }
        except Exception as error:  # noqa: BLE001 - projeção continua disponível
            LOGGER.exception("Projeção concluída, mas não foi possível salvar no diário")
            journal = {"salvo": False, "erro": f"{type(error).__name__}: {error}"}

        LOGGER.info("Projeção web concluída | diario_salvo=%s", journal["salvo"])
        self._send_json(200, {"resultado": result, "diario": journal})
