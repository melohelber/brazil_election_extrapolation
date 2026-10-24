"""Casos de uso sem persistência para a interface web."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging
from typing import Any

from apuracao_presidente.application.snapshot import SecondRoundSource
from apuracao_presidente.config import (
    DEFAULT_MOCK_PATH,
    FIRST_ROUND_TURNOUT_PATH,
    RESULT_LOCATIONS,
    SECOND_ROUND_ELECTION,
)
from apuracao_presidente.domain.projection import project_election
from apuracao_presidente.infrastructure.mock_source import MockSecondRoundSource
from apuracao_presidente.infrastructure.storage import read_json
from apuracao_presidente.infrastructure.tse_client import TSEClient, TSESecondRoundSource


def collect_web_snapshot(
    *,
    mock: bool = False,
    workers: int = 8,
    attempts: int = 3,
    timeout: float = 20,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Coleta todas as localidades e devolve um snapshot serializável."""

    if workers <= 0 or attempts <= 0 or timeout <= 0:
        raise ValueError("workers, attempts e timeout devem ser positivos")

    active_logger = logger or logging.getLogger("apuracao_presidente.web")
    started_at = datetime.now().astimezone()
    source: SecondRoundSource
    if mock:
        source = MockSecondRoundSource(DEFAULT_MOCK_PATH, FIRST_ROUND_TURNOUT_PATH)
    else:
        source = TSESecondRoundSource(
            TSEClient(active_logger, attempts=attempts, timeout=timeout)
        )

    states: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    active_logger.info(
        "Coleta web iniciada | modo=%s | localidades=%d",
        "mock" if mock else "real",
        len(RESULT_LOCATIONS),
    )

    with ThreadPoolExecutor(max_workers=min(workers, len(RESULT_LOCATIONS))) as executor:
        futures = {
            executor.submit(source.load, location): location
            for location in RESULT_LOCATIONS
        }
        for future in as_completed(futures):
            location = futures[future]
            try:
                states[location] = future.result()
                active_logger.info("[%s] Coleta web OK", location.upper())
            except Exception as error:  # noqa: BLE001 - o erro precisa ir ao relatório por UF
                errors[location] = f"{type(error).__name__}: {error}"
                active_logger.exception("[%s] Coleta web falhou", location.upper())

    collection: dict[str, Any] = {
        "capturado_em": started_at.isoformat(),
        "eleicao": int(SECOND_ROUND_ELECTION),
        "turno": 2,
        "modo": "mock" if mock else "real",
        "status": "completo" if not errors else "incompleto",
        "estados": {
            location: states[location]
            for location in RESULT_LOCATIONS
            if location in states
        },
        "resumo_coleta": [
            {
                "local": location.upper(),
                "status": (
                    "erro" if location not in states
                    else "sem_votos" if states[location]["total_votos_apurados"] == 0
                    else "ok"
                ),
                "erro": errors.get(location),
            }
            for location in RESULT_LOCATIONS
        ],
    }
    if errors:
        collection["erros"] = {
            location: errors[location]
            for location in RESULT_LOCATIONS
            if location in errors
        }
    collection["pronto_para_projetar"] = all(
        item["status"] == "ok" for item in collection["resumo_coleta"]
    )
    active_logger.info(
        "Coleta web concluída | status=%s | sucesso=%d | erros=%d",
        collection["status"],
        len(states),
        len(errors),
    )
    return collection


def project_web_snapshot(collection: dict[str, Any]) -> dict[str, Any]:
    """Valida um snapshot completo e aplica o mesmo domínio usado pela CLI."""

    if collection.get("status") != "completo":
        raise ValueError("A projeção exige uma coleta completa")
    states = collection.get("estados", {})
    without_votes = [
        location.upper() for location in RESULT_LOCATIONS
        if int(states.get(location, {}).get("total_votos_apurados", 0)) == 0
    ]
    if without_votes:
        raise ValueError("Sem votos apurados em: " + ", ".join(without_votes))
    reference = read_json(FIRST_ROUND_TURNOUT_PATH)
    result = project_election(collection, reference)
    return {
        "capturado_em": collection.get("capturado_em"),
        "modo": collection.get("modo", "real"),
        **result,
    }
