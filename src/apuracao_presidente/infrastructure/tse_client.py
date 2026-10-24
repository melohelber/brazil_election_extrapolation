"""Cliente e validadores para os arquivos oficiais de resultados do TSE."""

import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apuracao_presidente.config import (
    FIRST_ROUND_ELECTION,
    FLAVIO_NUMBER,
    LULA_NUMBER,
    SECOND_ROUND_ELECTION,
    TSE_CODES,
    tse_url,
)


class TSEClient:
    """Baixa documentos do TSE com timeout, retentativas e logs."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        attempts: int = 3,
        timeout: float = 20,
    ) -> None:
        if attempts <= 0 or timeout <= 0:
            raise ValueError("attempts e timeout devem ser positivos")
        self.logger = logger
        self.attempts = attempts
        self.timeout = timeout

    def fetch(self, election: str, location: str) -> dict[str, Any]:
        url = tse_url(election, location)
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "apuracao-presidente-2026/1.0",
            },
        )

        for attempt in range(1, self.attempts + 1):
            try:
                self.logger.debug(
                    "[%s] Requisição %d/%d: %s",
                    location.upper(), attempt, self.attempts, url,
                )
                with urlopen(request, timeout=self.timeout) as response:
                    if response.status != 200:
                        raise RuntimeError(f"HTTP inesperado: {response.status}")
                    return json.load(response)
            except (
                HTTPError,
                URLError,
                TimeoutError,
                json.JSONDecodeError,
                OSError,
            ) as error:
                if attempt == self.attempts:
                    self.logger.error(
                        "[%s] Falha definitiva após %d tentativa(s): %s",
                        location.upper(), self.attempts, error,
                        exc_info=True,
                    )
                    raise
                delay = 2 ** (attempt - 1)
                self.logger.warning(
                    "[%s] Tentativa %d/%d falhou: %s. Nova tentativa em %ds.",
                    location.upper(), attempt, self.attempts, error, delay,
                )
                time.sleep(delay)

        raise RuntimeError(f"Fluxo de tentativas inválido para {location}")


class TSESecondRoundSource:
    """Fonte de dados normalizados do segundo turno usando o TSE real."""

    def __init__(self, client: TSEClient) -> None:
        self.client = client

    def load(self, location: str) -> dict[str, Any]:
        return normalize_second_round(
            location,
            self.client.fetch(SECOND_ROUND_ELECTION, location),
        )


def validate_scope(
    data: dict[str, Any],
    *,
    election: str,
    round_number: str,
    location: str,
) -> None:
    if str(data.get("ele")) != election:
        raise ValueError(f"eleição inesperada: {data.get('ele')}")
    if str(data.get("t")) != round_number:
        raise ValueError(f"turno inesperado: {data.get('t')}")
    expected_code = TSE_CODES[location]
    if str(data.get("cdabr")) != expected_code:
        raise ValueError(f"abrangência inesperada: {data.get('cdabr')}")


def extract_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai nome e votos de todos os candidatos a presidente."""

    candidates: list[dict[str, Any]] = []
    for office in data["carg"]:
        if str(office.get("cd")) != "1":
            continue
        for coalition in office["agr"]:
            for party in coalition["par"]:
                for candidate in party["cand"]:
                    candidates.append(
                        {
                            "nome": candidate["nmu"],
                            "votos": int(candidate["vap"]),
                        }
                    )
    if not candidates:
        raise ValueError("nenhum candidato a presidente encontrado")
    return sorted(candidates, key=lambda item: item["votos"], reverse=True)


def extract_second_round_candidate_votes(data: dict[str, Any]) -> dict[str, int]:
    votes_by_number: dict[str, int] = {}
    for office in data["carg"]:
        if str(office.get("cd")) != "1":
            continue
        for coalition in office["agr"]:
            for party in coalition["par"]:
                for candidate in party["cand"]:
                    votes_by_number[str(candidate["n"])] = int(candidate["vap"])

    missing = {FLAVIO_NUMBER, LULA_NUMBER} - votes_by_number.keys()
    if missing:
        raise ValueError(
            "candidato(s) não encontrado(s): " + ", ".join(sorted(missing))
        )
    return votes_by_number


def normalize_second_round(
    location: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Valida e reduz a resposta do TSE ao formato usado pela projeção."""

    validate_scope(
        data,
        election=SECOND_ROUND_ELECTION,
        round_number="2",
        location=location,
    )
    candidate_votes = extract_second_round_candidate_votes(data)
    votes = data["v"]
    total = int(votes["tv"])
    flavio = candidate_votes[FLAVIO_NUMBER]
    lula = candidate_votes[LULA_NUMBER]
    blank = int(votes["vb"])
    null = int(votes["tvn"])

    if min(total, flavio, lula, blank, null) < 0:
        raise ValueError("o TSE retornou uma quantidade negativa de votos")
    component_sum = flavio + lula + blank + null
    if component_sum != total:
        raise ValueError(
            "total inconsistente: "
            f"total={total}, candidatos+brancos+nulos={component_sum}"
        )

    return {
        "total_votos_apurados": total,
        "votos_flavio_bolsonaro": flavio,
        "votos_lula": lula,
        "votos_brancos": blank,
        "votos_nulos": null,
        "apuracao_finalizada": str(data.get("and", "")).lower() == "f",
        "gerado_em_tse": {
            "data": data.get("dg"),
            "hora": data.get("hg"),
            "id": data.get("idg"),
        },
    }


def normalize_first_round(
    location: str,
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Valida e separa candidatos e comparecimento do primeiro turno."""

    validate_scope(
        data,
        election=FIRST_ROUND_ELECTION,
        round_number="1",
        location=location,
    )
    votes = data["v"]
    turnout = {
        "total_votos_primeiro_turno": int(votes["tv"]),
        "votos_validos_primeiro_turno": int(votes["vv"]),
        "brancos_primeiro_turno": int(votes["vb"]),
        "nulos_primeiro_turno": int(votes["tvn"]),
    }
    if min(turnout.values()) < 0:
        raise ValueError("o TSE retornou uma quantidade negativa de votos")
    if (
        turnout["votos_validos_primeiro_turno"]
        + turnout["brancos_primeiro_turno"]
        + turnout["nulos_primeiro_turno"]
        != turnout["total_votos_primeiro_turno"]
    ):
        raise ValueError("total do primeiro turno inconsistente")
    return extract_candidates(data), turnout
