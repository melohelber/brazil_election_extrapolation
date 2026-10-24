"""Leitura e gravação segura de documentos JSON."""

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json_atomic(content: Any, path: Path) -> None:
    """Grava JSON sem deixar um arquivo parcial em caso de falha."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(content, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
