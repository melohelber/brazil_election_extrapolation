"""Orquestra a coleta e a projeção de um snapshot do segundo turno."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from apuracao_presidente.config import (
    DEFAULT_MOCK_PATH,
    FIRST_ROUND_TURNOUT_PATH,
    RESULT_LOCATIONS,
    SECOND_ROUND_ELECTION,
)
from apuracao_presidente.application.first_round import load_projection_reference
from apuracao_presidente.domain.projection import project_election
from apuracao_presidente.infrastructure.storage import write_json_atomic
from apuracao_presidente.infrastructure.mock_source import MockSecondRoundSource
from apuracao_presidente.infrastructure.tse_client import (
    TSEClient,
    TSESecondRoundSource,
)


@dataclass(frozen=True)
class SnapshotOptions:
    output_dir: Path
    workers: int = 8
    attempts: int = 3
    timeout: float = 20
    assume_yes: bool = False
    mock: bool = False
    mock_path: Path = DEFAULT_MOCK_PATH

    def validate(self) -> None:
        if self.workers <= 0 or self.attempts <= 0 or self.timeout <= 0:
            raise ValueError("workers, attempts e timeout devem ser positivos")


class SecondRoundSource(Protocol):
    def load(self, location: str) -> dict[str, Any]: ...


def collect_location(
    location: str,
    source: SecondRoundSource,
    logger: logging.Logger,
) -> dict[str, Any]:
    logger.info("[%s] Iniciando coleta", location.upper())
    normalized = source.load(location)
    logger.info(
        "[%s] OK | total=%d | Flávio=%d | Lula=%d | brancos=%d | nulos=%d",
        location.upper(),
        normalized["total_votos_apurados"],
        normalized["votos_flavio_bolsonaro"],
        normalized["votos_lula"],
        normalized["votos_brancos"],
        normalized["votos_nulos"],
    )
    return normalized


def show_collection_summary(
    states: dict[str, dict[str, Any]],
    errors: dict[str, str],
) -> None:
    print("\nResultado da coleta:")
    for location in RESULT_LOCATIONS:
        if location in states:
            status = (
                "BASE 1º TURNO"
                if states[location]["total_votos_apurados"] == 0
                else "OK"
            )
            print(f"  {location.upper():<8} {status}")
        else:
            print(f"  {location.upper():<8} ERRO - {errors[location]}")


def confirm_result() -> bool:
    while True:
        answer = input("\nGerar o JSON de resultado? [Y/N]: ").strip().lower()
        if answer in {"y", "yes", "s", "sim"}:
            return True
        if answer in {"n", "no", "nao", "não"}:
            return False
        print("Resposta inválida. Digite Y ou N.")


def run_snapshot(
    options: SnapshotOptions,
    logger: logging.Logger,
    started_at: datetime,
) -> int:
    options.validate()
    execution_id = started_at.strftime("%Y%m%d_%H%M%S")
    output_dir = options.output_dir.resolve()
    mock_suffix = "_mock" if options.mock else ""
    collection_path = output_dir / f"coleta{mock_suffix}_{execution_id}.json"
    result_path = output_dir / f"resultado{mock_suffix}_{execution_id}.json"

    logger.info(
        "Início | eleição=%s | localidades=%d | modo=%s | coleta=%s",
        SECOND_ROUND_ELECTION,
        len(RESULT_LOCATIONS),
        "mock" if options.mock else "real",
        collection_path,
    )
    if options.mock:
        logger.warning(
            "MODO MOCK ATIVO | nenhuma requisição será feita ao TSE | cenário=%s",
            options.mock_path.resolve(),
        )
        print("\n=== MODO MOCK: dados locais, sem acesso ao TSE ===")
        source: SecondRoundSource = MockSecondRoundSource(
            options.mock_path,
            FIRST_ROUND_TURNOUT_PATH,
        )
    else:
        source = TSESecondRoundSource(
            TSEClient(
                logger,
                attempts=options.attempts,
                timeout=options.timeout,
            )
        )
    states: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(
        max_workers=min(options.workers, len(RESULT_LOCATIONS))
    ) as executor:
        futures = {
            executor.submit(collect_location, location, source, logger): location
            for location in RESULT_LOCATIONS
        }
        for future in as_completed(futures):
            location = futures[future]
            try:
                states[location] = future.result()
            except Exception as error:
                errors[location] = f"{type(error).__name__}: {error}"
                logger.error(
                    "[%s] Local excluído do snapshot: %s",
                    location.upper(),
                    error,
                )

    collection: dict[str, Any] = {
        "capturado_em": started_at.isoformat(),
        "eleicao": int(SECOND_ROUND_ELECTION),
        "turno": 2,
        "modo": "mock" if options.mock else "real",
        "status": "completo" if not errors else "incompleto",
        "estados": {
            location: states[location]
            for location in RESULT_LOCATIONS
            if location in states
        },
    }
    if errors:
        collection["erros"] = {
            location: errors[location]
            for location in RESULT_LOCATIONS
            if location in errors
        }

    write_json_atomic(collection, collection_path)
    logger.info("JSON de coleta salvo: %s", collection_path)
    show_collection_summary(states, errors)

    if errors:
        logger.error(
            "Coleta incompleta: %d/%d localidades; resultado não gerado; falhas=%s",
            len(states),
            len(RESULT_LOCATIONS),
            ",".join(location.upper() for location in errors),
        )
        print(f"\nSnapshot incompleto preservado em: {collection_path}")
        return 1

    if not options.assume_yes and not confirm_result():
        logger.info("Geração do resultado cancelada pelo usuário")
        print(f"\nColeta preservada em: {collection_path}")
        return 0

    logger.info("Carregando referência completa do primeiro turno")
    reference = load_projection_reference()
    logger.info("Iniciando cálculo da extrapolação")
    result = project_election(collection, reference)
    write_json_atomic(result, result_path)
    logger.info("JSON de resultado salvo: %s", result_path)
    print(f"\nColeta:   {collection_path}")
    print(f"Resultado: {result_path}")
    return 0
