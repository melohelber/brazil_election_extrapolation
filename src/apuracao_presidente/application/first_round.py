"""Atualiza a base oficial e estática do primeiro turno."""

import logging
from typing import Any

from apuracao_presidente.config import (
    FIRST_ROUND_CANDIDATES_DIR,
    FIRST_ROUND_ELECTION,
    FIRST_ROUND_LOCATIONS,
    FIRST_ROUND_TURNOUT_PATH,
)
from apuracao_presidente.infrastructure.storage import write_json_atomic
from apuracao_presidente.infrastructure.tse_client import (
    TSEClient,
    normalize_first_round,
)


def update_first_round_database(
    client: TSEClient,
    logger: logging.Logger,
) -> None:
    """Baixa tudo, valida tudo e somente depois substitui a base local."""

    candidates_by_location: dict[str, list[dict[str, Any]]] = {}
    turnout_by_location: dict[str, dict[str, int]] = {}

    for location in FIRST_ROUND_LOCATIONS:
        logger.info("[%s] Coletando primeiro turno", location.upper())
        data = client.fetch(FIRST_ROUND_ELECTION, location)
        candidates, turnout = normalize_first_round(location, data)
        candidates_by_location[location] = candidates
        if location != "brasil":
            turnout_by_location[location] = turnout
        logger.info(
            "[%s] OK | candidatos=%d | comparecimento=%d",
            location.upper(),
            len(candidates),
            turnout["total_votos_primeiro_turno"],
        )

    for location, candidates in candidates_by_location.items():
        write_json_atomic(
            candidates,
            FIRST_ROUND_CANDIDATES_DIR / f"{location}.json",
        )

    reference = {
        "eleicao": int(FIRST_ROUND_ELECTION),
        "turno": 1,
        "cargo": "Presidente",
        "fonte": "Tribunal Superior Eleitoral",
        "campo_usado_como_comparecimento": "v.tv",
        "descricao": (
            "Total de pessoas que votaram no primeiro turno, incluindo votos "
            "válidos, brancos e nulos."
        ),
        "locais": turnout_by_location,
    }
    write_json_atomic(reference, FIRST_ROUND_TURNOUT_PATH)
    logger.info(
        "Base do primeiro turno atualizada | candidatos=%s | comparecimento=%s",
        FIRST_ROUND_CANDIDATES_DIR,
        FIRST_ROUND_TURNOUT_PATH,
    )
