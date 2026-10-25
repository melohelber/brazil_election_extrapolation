"""Atualiza a base oficial e estática do primeiro turno."""

import logging
from typing import Any

from apuracao_presidente.config import (
    FIRST_ROUND_CANDIDATES_DIR,
    FIRST_ROUND_ELECTION,
    FIRST_ROUND_LOCATIONS,
    FIRST_ROUND_TURNOUT_PATH,
    RESULT_LOCATIONS,
)
from apuracao_presidente.infrastructure.storage import (
    read_json,
    write_json_atomic,
)
from apuracao_presidente.infrastructure.tse_client import (
    TSEClient,
    normalize_first_round,
)


FIRST_ROUND_CANDIDATE_NAMES = {
    "FLAVIO BOLSONARO": "votos_flavio_bolsonaro_primeiro_turno",
    "LULA": "votos_lula_primeiro_turno",
}


def load_projection_reference() -> dict[str, Any]:
    """Combina comparecimento e votos nominais usados no fallback sem apuração."""

    reference = read_json(FIRST_ROUND_TURNOUT_PATH)
    locations = reference.get("locais")
    if not isinstance(locations, dict):
        raise ValueError("A referência do primeiro turno não contém 'locais'")

    for location in RESULT_LOCATIONS:
        turnout = locations.get(location)
        if not isinstance(turnout, dict):
            raise ValueError(
                f"Referência do primeiro turno ausente para {location.upper()}"
            )
        candidates = read_json(
            FIRST_ROUND_CANDIDATES_DIR / f"{location}.json"
        )
        votes_by_name = {
            str(candidate.get("nome")): int(candidate.get("votos", -1))
            for candidate in candidates
            if isinstance(candidate, dict)
        }
        for name, field in FIRST_ROUND_CANDIDATE_NAMES.items():
            if votes_by_name.get(name, -1) < 0:
                raise ValueError(
                    f"{name} ausente na base do primeiro turno de "
                    f"{location.upper()}"
                )
            turnout[field] = votes_by_name[name]

    return reference


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
