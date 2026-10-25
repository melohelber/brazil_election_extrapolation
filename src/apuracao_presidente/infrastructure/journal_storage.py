"""Persistência do diário web em disco local ou Vercel Blob."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class JournalObject:
    pathname: str
    url: str


class JournalStorage(Protocol):
    def put_json(self, pathname: str, payload: dict[str, Any]) -> JournalObject: ...

    def list_objects(self, prefix: str) -> list[JournalObject]: ...


class LocalJournalStorage:
    """Backend de desenvolvimento que mantém o mesmo layout do Blob."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put_json(self, pathname: str, payload: dict[str, Any]) -> JournalObject:
        target = (self.root / pathname).resolve()
        if self.root not in target.parents:
            raise ValueError("Caminho inválido para o diário")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return JournalObject(pathname=pathname, url=target.as_uri())

    def list_objects(self, prefix: str) -> list[JournalObject]:
        base = (self.root / prefix).resolve()
        if self.root not in base.parents and base != self.root:
            raise ValueError("Prefixo inválido para o diário")
        if not base.exists():
            return []
        return [
            JournalObject(
                pathname=path.relative_to(self.root).as_posix(),
                url=path.as_uri(),
            )
            for path in sorted(base.rglob("*.json"))
        ]


class BlobJournalStorage:
    """Backend persistente do diário, conectado ao Vercel Blob."""

    def put_json(self, pathname: str, payload: dict[str, Any]) -> JournalObject:
        from vercel.blob import put

        body = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        blob = put(
            pathname,
            body,
            access="public",
            content_type="application/json; charset=utf-8",
            overwrite=True,
            cache_control_max_age=60,
        )
        return JournalObject(pathname=blob.pathname, url=blob.url)

    def list_objects(self, prefix: str) -> list[JournalObject]:
        from vercel.blob import list_objects

        objects: list[JournalObject] = []
        cursor: str | None = None
        while True:
            page = list_objects(prefix=prefix, limit=1000, cursor=cursor)
            objects.extend(
                JournalObject(pathname=item.pathname, url=item.url)
                for item in page.blobs
            )
            if not page.has_more:
                break
            cursor = page.cursor
        return objects


def journal_storage(project_root: Path) -> JournalStorage:
    """Seleciona Blob em produção e disco somente no desenvolvimento local."""

    if os.environ.get("BLOB_READ_WRITE_TOKEN"):
        return BlobJournalStorage()
    if os.environ.get("VERCEL"):
        raise RuntimeError("BLOB_READ_WRITE_TOKEN não configurado no projeto Vercel")
    return LocalJournalStorage(project_root / "var" / "web_diary")
