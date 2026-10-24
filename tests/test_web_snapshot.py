import logging
import unittest

from apuracao_presidente.application.web_snapshot import (
    collect_web_snapshot,
    project_web_snapshot,
)
from apuracao_presidente.config import RESULT_LOCATIONS


class WebSnapshotTests(unittest.TestCase):
    def test_mock_collects_all_locations_and_projects_brazil(self):
        collection = collect_web_snapshot(mock=True, logger=logging.getLogger("test"))

        self.assertEqual(collection["status"], "completo")
        self.assertEqual(len(collection["estados"]), len(RESULT_LOCATIONS))
        self.assertEqual(len(collection["resumo_coleta"]), len(RESULT_LOCATIONS))
        self.assertTrue(all(item["status"] == "ok" for item in collection["resumo_coleta"]))

        result = project_web_snapshot(collection)
        self.assertEqual(len(result["resultados"]), len(RESULT_LOCATIONS) + 1)
        self.assertEqual(result["resultados"][-1]["local"], "BRASIL")
        self.assertIsNotNone(
            result["resultados"][-1]["projetado"]["resultado_extrapolado"]
        )

    def test_incomplete_collection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "coleta completa"):
            project_web_snapshot({"status": "incompleto", "estados": {}})


if __name__ == "__main__":
    unittest.main()
