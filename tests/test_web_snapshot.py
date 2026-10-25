import logging
import unittest
from unittest.mock import patch

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
        self.assertTrue(all(
            item["percentual_secoes_totalizadas"] == 25.0
            for item in collection["resumo_coleta"]
        ))

        result = project_web_snapshot(collection)
        self.assertEqual(len(result["resultados"]), len(RESULT_LOCATIONS) + 1)
        self.assertEqual(result["resultados"][-1]["local"], "BRASIL")
        self.assertIsNotNone(
            result["resultados"][-1]["projetado"]["resultado_extrapolado"]
        )

    def test_incomplete_collection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "coleta completa"):
            project_web_snapshot({"status": "incompleto", "estados": {}})

    def test_zero_votes_use_first_round_fallback_and_allow_projection(self):
        with patch(
            "apuracao_presidente.application.web_snapshot.MockSecondRoundSource.load",
            return_value={
                "total_votos_apurados": 0,
                "votos_flavio_bolsonaro": 0,
                "votos_lula": 0,
            },
        ):
            collection = collect_web_snapshot(mock=True)
        self.assertEqual(collection["status"], "completo")
        self.assertTrue(collection["pronto_para_projetar"])
        self.assertTrue(all(row["status"] == "sem_votos" for row in collection["resumo_coleta"]))
        result = project_web_snapshot(collection)
        self.assertIsNotNone(
            result["resultados"][-1]["projetado"]["resultado_extrapolado"]
        )
        self.assertTrue(all(
            item["projetado"]["origem_projecao"]
            == "primeiro_turno_redistribuido"
            for item in result["resultados"][:-1]
        ))


if __name__ == "__main__":
    unittest.main()
