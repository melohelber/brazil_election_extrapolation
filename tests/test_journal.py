import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from apuracao_presidente.application.journal import (
    list_journal_history,
    save_journal_entry,
)
from apuracao_presidente.application.web_snapshot import (
    collect_web_snapshot,
    project_web_snapshot,
)
from apuracao_presidente.infrastructure.journal_storage import (
    BlobJournalStorage,
    LocalJournalStorage,
)


class DiarioWebTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = LocalJournalStorage(self.root)
        self.collection = collect_web_snapshot(mock=True)
        self.collection["capturado_em"] = "2026-10-25T19:31:47-03:00"
        self.result = project_web_snapshot(self.collection)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_salva_jsons_completos_e_lista_resumo(self) -> None:
        summary = save_journal_entry(self.collection, self.result, self.storage)

        self.assertEqual(summary["id"], "20261025T1931")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["localidades_apuracao_atual"], 28)
        self.assertEqual(summary["localidades_base_primeiro_turno"], 0)

        collection_path = self.root / summary["coleta"]["pathname"]
        result_path = self.root / summary["resultado"]["pathname"]
        self.assertEqual(json.loads(collection_path.read_text())["estados"], self.collection["estados"])
        self.assertEqual(json.loads(result_path.read_text())["resultados"], self.result["resultados"])

        history = list_journal_history(self.storage, date="2026-10-25", mock=True)
        self.assertEqual(history["total"], 1)
        entry = history["rodadas"][0]
        self.assertEqual(entry["capturado_em"], "2026-10-25T19:31:00-03:00")
        self.assertAlmostEqual(
            entry["flavio_bolsonaro_percentual"] + entry["lula_percentual"],
            100,
            places=4,
        )
        self.assertIn("coleta_20261025T1931.json", entry["coleta_url"])
        self.assertIn("resultado_20261025T1931.json", entry["resultado_url"])

    def test_mesmo_minuto_e_idempotente(self) -> None:
        save_journal_entry(self.collection, self.result, self.storage)
        second = dict(self.collection)
        second["capturado_em"] = "2026-10-25T19:31:59-03:00"
        second_result = project_web_snapshot(second)
        save_journal_entry(second, second_result, self.storage)

        history = list_journal_history(self.storage, date="2026-10-25", mock=True)
        self.assertEqual(history["total"], 1)
        result_files = list((self.root / "diario/mock/resultados/2026/10/25").glob("*.json"))
        self.assertEqual(len(result_files), 1)

    def test_falha_preserva_coleta_sem_inventar_resultado(self) -> None:
        failed = dict(self.collection)
        failed["status"] = "incompleto"
        failed["pronto_para_projetar"] = False
        failed["resumo_coleta"] = [
            {"local": "AC", "status": "erro", "erro": "timeout"}
        ]
        failed["erros"] = {"ac": "timeout"}

        summary = save_journal_entry(failed, None, self.storage)
        history = list_journal_history(self.storage, date="2026-10-25", mock=True)

        self.assertEqual(summary["status"], "erro")
        self.assertIsNone(summary["resultado"])
        self.assertEqual(history["rodadas"][0]["status"], "erro")
        self.assertIsNone(history["rodadas"][0]["resultado_url"])
        self.assertFalse((self.root / "diario/mock/resultados").exists())


class BlobJournalStorageTest(unittest.TestCase):
    def test_usa_funcoes_publicas_do_sdk_python(self) -> None:
        calls: dict[str, object] = {}
        package = types.ModuleType("vercel")
        package.__path__ = []
        blob_module = types.ModuleType("vercel.blob")

        def fake_put(pathname: str, body: bytes, **options: object) -> object:
            calls["put"] = (pathname, body, options)
            return types.SimpleNamespace(pathname=pathname, url=f"https://blob.test/{pathname}")

        def fake_list_objects(**options: object) -> object:
            calls["list"] = options
            return types.SimpleNamespace(
                blobs=[types.SimpleNamespace(pathname="diario/resumo.json", url="https://blob.test/resumo")],
                has_more=False,
                cursor=None,
            )

        blob_module.put = fake_put
        blob_module.list_objects = fake_list_objects
        with patch.dict(sys.modules, {"vercel": package, "vercel.blob": blob_module}):
            storage = BlobJournalStorage()
            saved = storage.put_json("diario/resumo.json", {"ok": True})
            listed = storage.list_objects("diario/")

        self.assertEqual(saved.pathname, "diario/resumo.json")
        self.assertEqual(listed[0].pathname, "diario/resumo.json")
        self.assertEqual(calls["list"], {"prefix": "diario/", "limit": 1000, "cursor": None})
        self.assertEqual(calls["put"][2]["overwrite"], True)


if __name__ == "__main__":
    unittest.main()
