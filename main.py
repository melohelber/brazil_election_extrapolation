#!/usr/bin/env python3

"""Ponto de entrada para executar o projeto diretamente do código-fonte."""

import sys
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SOURCE_DIR))

from apuracao_presidente.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
