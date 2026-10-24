"""Interface de linha de comando do projeto."""

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apuracao_presidente.application.first_round import (
    update_first_round_database,
)
from apuracao_presidente.application.snapshot import SnapshotOptions, run_snapshot
from apuracao_presidente.config import (
    DEFAULT_MOCK_PATH,
    LOGS_DIR,
    MOCK_SNAPSHOTS_DIR,
    SNAPSHOTS_DIR,
)
from apuracao_presidente.infrastructure.logging_setup import configure_logger
from apuracao_presidente.infrastructure.tse_client import TSEClient


BRASILIA_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Coleta e projeta a apuração presidencial de 2026."
    )
    parser.add_argument(
        "comando",
        nargs="?",
        choices=("snapshot", "atualizar-primeiro-turno"),
        default="snapshot",
        help="Operação; sem argumento, executa snapshot",
    )
    parser.add_argument(
        "--pasta-saida",
        type=Path,
        default=None,
        help="Pasta que receberá os JSONs; o padrão depende do modo",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--tentativas", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Gera o resultado sem perguntar; destinado a automações e testes",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usa o cenário local e não acessa o TSE",
    )
    parser.add_argument(
        "--arquivo-mock",
        type=Path,
        default=DEFAULT_MOCK_PATH,
        help="JSON do cenário usado com --mock",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.comando != "snapshot" and args.mock:
        parser.error("--mock só pode ser usado no comando snapshot")
    started_at = datetime.now(BRASILIA_TIMEZONE)
    execution_id = started_at.strftime("%Y%m%d_%H%M%S")
    if args.comando == "atualizar-primeiro-turno":
        prefix = "atualizacao_primeiro_turno"
    elif args.mock:
        prefix = "execucao_mock"
    else:
        prefix = "execucao"
    logger, log_path = configure_logger(
        LOGS_DIR,
        execution_id,
        prefix=prefix,
    )

    try:
        if args.comando == "atualizar-primeiro-turno":
            client = TSEClient(
                logger,
                attempts=args.tentativas,
                timeout=args.timeout,
            )
            update_first_round_database(client, logger)
            code = 0
        else:
            output_dir = args.pasta_saida or (
                MOCK_SNAPSHOTS_DIR if args.mock else SNAPSHOTS_DIR
            )
            code = run_snapshot(
                SnapshotOptions(
                    output_dir=output_dir,
                    workers=args.workers,
                    attempts=args.tentativas,
                    timeout=args.timeout,
                    assume_yes=args.yes,
                    mock=args.mock,
                    mock_path=args.arquivo_mock,
                ),
                logger,
                started_at,
            )
    except Exception:
        logger.exception("Falha na execução")
        print(f"\nFalha. Consulte o log: {log_path}")
        return 2

    logger.info("Fim da execução | código=%d | log=%s", code, log_path)
    return code
