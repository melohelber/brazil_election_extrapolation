"""Execução, persistência e consulta do diário minuto a minuto."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import PurePosixPath
import re
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from apuracao_presidente.application.web_snapshot import (
    collect_web_snapshot,
    project_web_snapshot,
)
from apuracao_presidente.infrastructure.journal_storage import (
    JournalObject,
    JournalStorage,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
SUMMARY_PATTERN = re.compile(
    r"^(?P<run_id>\d{8}T\d{4})__(?P<status>ok|erro)"
    r"(?:__f(?P<flavio>\d{7})__l(?P<lula>\d{7}))?"
    r"__a(?P<apuracao>\d{2})__b(?P<base>\d{2})\.json$"
)


def _captured_datetime(value: str | None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SAO_PAULO)
        return parsed.astimezone(SAO_PAULO)
    return datetime.now(SAO_PAULO)


def run_id_for(value: str | None) -> str:
    """Identificador idempotente por minuto no horário de Brasília."""

    return _captured_datetime(value).strftime("%Y%m%dT%H%M")


def _candidate_percentages(
    result: dict[str, Any] | None,
) -> tuple[float | None, float | None]:
    if not result:
        return None, None
    brazil = next(
        (entry for entry in result.get("resultados", []) if entry.get("local") == "BRASIL"),
        None,
    )
    projected = brazil and brazil.get("projetado", {}).get("resultado_extrapolado")
    if not projected:
        return None, None
    return (
        float(projected["flavio_bolsonaro"]["percentual_sobre_validos"]),
        float(projected["lula"]["percentual_sobre_validos"]),
    )


def _paths(
    collection: dict[str, Any], result: dict[str, Any] | None
) -> dict[str, str | None]:
    captured = _captured_datetime(collection.get("capturado_em"))
    date_path = captured.strftime("%Y/%m/%d")
    run_id = run_id_for(collection.get("capturado_em"))
    mode = collection.get("modo", "real")
    base = f"diario/{mode}"
    collection_path = f"{base}/coletas/{date_path}/coleta_{run_id}.json"
    result_path = (
        f"{base}/resultados/{date_path}/resultado_{run_id}.json" if result else None
    )
    rows = collection.get("resumo_coleta", [])
    current_count = sum(item.get("status") == "ok" for item in rows)
    fallback_count = sum(item.get("status") == "sem_votos" for item in rows)
    flavio, lula = _candidate_percentages(result)
    status = "ok" if result is not None else "erro"
    percentage_part = ""
    if flavio is not None and lula is not None:
        percentage_part = f"__f{round(flavio * 10000):07d}__l{round(lula * 10000):07d}"
    summary_name = (
        f"{run_id}__{status}{percentage_part}"
        f"__a{current_count:02d}__b{fallback_count:02d}.json"
    )
    summary_path = f"{base}/resumos/{date_path}/{summary_name}"
    return {
        "run_id": run_id,
        "collection": collection_path,
        "result": result_path,
        "summary": summary_path,
    }


def save_journal_entry(
    collection: dict[str, Any],
    result: dict[str, Any] | None,
    storage: JournalStorage,
    *,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Grava os JSONs completos e publica o resumo somente ao final."""

    active_logger = logger or logging.getLogger("apuracao_presidente.journal")
    paths = _paths(collection, result)
    collection_blob = storage.put_json(str(paths["collection"]), collection)
    result_blob = storage.put_json(str(paths["result"]), result) if result else None
    flavio, lula = _candidate_percentages(result)
    rows = collection.get("resumo_coleta", [])
    summary = {
        "id": paths["run_id"],
        "capturado_em": collection.get("capturado_em"),
        "modo": collection.get("modo", "real"),
        "status": "ok" if result is not None else "erro",
        "flavio_bolsonaro_percentual": flavio,
        "lula_percentual": lula,
        "localidades_apuracao_atual": sum(item.get("status") == "ok" for item in rows),
        "localidades_base_primeiro_turno": sum(
            item.get("status") == "sem_votos" for item in rows
        ),
        "erros": collection.get("erros", {}),
        "coleta": {"pathname": collection_blob.pathname, "url": collection_blob.url},
        "resultado": (
            {"pathname": result_blob.pathname, "url": result_blob.url}
            if result_blob
            else None
        ),
    }
    summary_blob = storage.put_json(str(paths["summary"]), summary)
    summary["resumo"] = {"pathname": summary_blob.pathname, "url": summary_blob.url}
    active_logger.info(
        "Diário salvo | id=%s | status=%s | resultado=%s",
        summary["id"],
        summary["status"],
        result_blob.pathname if result_blob else "indisponível",
    )
    return summary


def run_journal_entry(
    storage: JournalStorage,
    *,
    mock: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Coleta, projeta quando possível e persiste uma rodada completa."""

    active_logger = logger or logging.getLogger("apuracao_presidente.journal")
    collection = collect_web_snapshot(mock=mock, logger=active_logger)
    result = (
        project_web_snapshot(collection)
        if collection.get("pronto_para_projetar")
        else None
    )
    return save_journal_entry(collection, result, storage, logger=active_logger)


def _public_url(example: JournalObject, pathname: str) -> str:
    if example.url.startswith("file:"):
        return f"/api/history?arquivo={quote(pathname, safe='')}"
    marker = quote(example.pathname, safe="/")
    base = (
        example.url[: -len(marker)]
        if example.url.endswith(marker)
        else example.url.rsplit("/", 1)[0] + "/"
    )
    return base + quote(pathname, safe="/")


def list_journal_history(
    storage: JournalStorage,
    *,
    date: str | None = None,
    mock: bool = False,
    limit: int = 360,
) -> dict[str, Any]:
    """Lista um dia do diário usando apenas os nomes dos resumos."""

    selected = (
        datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=SAO_PAULO)
        if date
        else datetime.now(SAO_PAULO)
    )
    date_path = selected.strftime("%Y/%m/%d")
    mode = "mock" if mock else "real"
    prefix = f"diario/{mode}/resumos/{date_path}/"
    objects = storage.list_objects(prefix)
    entries: list[dict[str, Any]] = []
    for item in objects:
        match = SUMMARY_PATTERN.match(PurePosixPath(item.pathname).name)
        if not match:
            continue
        values = match.groupdict()
        run_id = values["run_id"]
        captured = datetime.strptime(run_id, "%Y%m%dT%H%M").replace(tzinfo=SAO_PAULO)
        result_path = f"diario/{mode}/resultados/{date_path}/resultado_{run_id}.json"
        collection_path = f"diario/{mode}/coletas/{date_path}/coleta_{run_id}.json"
        ok = values["status"] == "ok"
        entries.append(
            {
                "id": run_id,
                "capturado_em": captured.isoformat(),
                "status": values["status"],
                "flavio_bolsonaro_percentual": (
                    int(values["flavio"]) / 10000 if values["flavio"] else None
                ),
                "lula_percentual": int(values["lula"]) / 10000 if values["lula"] else None,
                "localidades_apuracao_atual": int(values["apuracao"]),
                "localidades_base_primeiro_turno": int(values["base"]),
                "coleta_url": _public_url(item, collection_path),
                "resultado_url": _public_url(item, result_path) if ok else None,
            }
        )
    entries.sort(key=lambda entry: entry["id"])
    if limit > 0:
        entries = entries[-limit:]
    return {
        "data": selected.strftime("%Y-%m-%d"),
        "modo": mode,
        "total": len(entries),
        "ultima_atualizacao": entries[-1]["capturado_em"] if entries else None,
        "rodadas": entries,
    }
