"""Persistência do diário web em disco local ou Vercel Blob."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


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

    api_url = "https://vercel.com/api/blob"

    def __init__(self) -> None:
        self.token = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
        if not self.token:
            raise RuntimeError("BLOB_READ_WRITE_TOKEN não configurado")

    def _request(
        self,
        method: str,
        *,
        params: dict[str, str | int],
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        store_id = self.token.split("_")[3] if len(self.token.split("_")) > 3 else "store"
        url = f"{self.api_url}?{urlencode(params)}"
        last_error: Exception | None = None
        for attempt in range(3):
            request_headers = {
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "apuracao-presidente-2026/1.0",
                "X-Api-Version": "11",
                "X-Api-Blob-Request-Id": f"{store_id}:{int(time.time() * 1000)}:{uuid4().hex[:8]}",
                "X-Api-Blob-Request-Attempt": str(attempt),
                **(headers or {}),
            }
            request = Request(url, data=body, headers=request_headers, method=method)
            try:
                with urlopen(request, timeout=30) as response:  # noqa: S310 - host fixo da Vercel
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                last_error = error
                if error.code < 500 or attempt == 2:
                    detail = error.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Vercel Blob HTTP {error.code}: {detail[:300]}") from error
            except URLError as error:
                last_error = error
                if attempt == 2:
                    raise RuntimeError(f"Vercel Blob indisponível: {error.reason}") from error
            time.sleep(0.25 * (2**attempt))
        raise RuntimeError(f"Falha inesperada no Vercel Blob: {last_error}")

    def put_json(self, pathname: str, payload: dict[str, Any]) -> JournalObject:
        body = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        blob = self._request(
            "PUT",
            params={"pathname": pathname},
            body=body,
            headers={
                "X-Vercel-Blob-Access": "public",
                "X-Content-Type": "application/json; charset=utf-8",
                "X-Allow-Overwrite": "1",
                "X-Add-Random-Suffix": "0",
                "X-Cache-Control-Max-Age": "60",
            },
        )
        return JournalObject(pathname=blob["pathname"], url=blob["url"])

    def list_objects(self, prefix: str) -> list[JournalObject]:
        objects: list[JournalObject] = []
        cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"prefix": prefix, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            page = self._request("GET", params=params)
            objects.extend(
                JournalObject(pathname=item["pathname"], url=item["url"])
                for item in page.get("blobs", [])
            )
            if not page.get("hasMore"):
                break
            cursor = page.get("cursor")
        return objects


def journal_storage(project_root: Path) -> JournalStorage:
    """Seleciona Blob em produção e disco somente no desenvolvimento local."""

    if os.environ.get("BLOB_READ_WRITE_TOKEN"):
        return BlobJournalStorage()
    if os.environ.get("VERCEL"):
        raise RuntimeError("BLOB_READ_WRITE_TOKEN não configurado no projeto Vercel")
    return LocalJournalStorage(project_root / "var" / "web_diary")
