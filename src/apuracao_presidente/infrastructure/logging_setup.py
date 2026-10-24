"""Configuração uniforme dos logs de uma execução."""

import logging
import sys
from pathlib import Path


def configure_logger(
    logs_dir: Path,
    execution_id: str,
    *,
    prefix: str = "execucao",
) -> tuple[logging.Logger, Path]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{prefix}_{execution_id}.log"

    logger = logging.getLogger("apuracao_presidente")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger, log_path
