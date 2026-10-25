import json
import os
from pathlib import Path
import tempfile
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
    def test_grava_e_lista_pela_api_http_do_blob(self) -> None:
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_store_test"}):
            storage = BlobJournalStorage()
        with patch.object(
            storage,
            "_request",
            side_effect=[
                {"pathname": "diario/resumo.json", "url": "https://blob.test/resumo"},
                {
                    "blobs": [
                        {"pathname": "diario/resumo.json", "url": "https://blob.test/resumo"}
                    ],
                    "hasMore": False,
                },
            ],
        ) as request:
            saved = storage.put_json("diario/resumo.json", {"ok": True})
            listed = storage.list_objects("diario/")

        self.assertEqual(saved.pathname, "diario/resumo.json")
        self.assertEqual(listed[0].pathname, "diario/resumo.json")
        self.assertEqual(request.call_args_list[0].args, ("PUT",))
        self.assertEqual(request.call_args_list[0].kwargs["params"], {"pathname": "diario/resumo.json"})
        self.assertEqual(request.call_args_list[1].kwargs["params"], {"prefix": "diario/", "limit": 1000})


if __name__ == "__main__":
    unittest.main()
