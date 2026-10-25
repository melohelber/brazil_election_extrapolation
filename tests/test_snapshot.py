#!/usr/bin/env python3

import json
import logging
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import apuracao_presidente.application.snapshot as snapshot
from apuracao_presidente.config import (
    DEFAULT_MOCK_PATH,
    FIRST_ROUND_TURNOUT_PATH,
    RESULT_LOCATIONS,
    tse_url,
)
from apuracao_presidente.infrastructure.mock_source import MockSecondRoundSource
from apuracao_presidente.infrastructure.tse_client import normalize_second_round


def dados_tse(*, codigo: str = "ce", finalizada: bool = False) -> dict:
    return {
        "ele": "6258",
        "t": "2",
        "cdabr": codigo,
        "and": "f" if finalizada else "n",
        "dg": "25/10/2026",
        "hg": "19:30:00",
        "idg": "123",
        "s": {"ts": "1000", "st": "127", "pst": "12,70", "pstn": "12.7"},
        "carg": [
            {
                "cd": "1",
                "agr": [
                    {
                        "par": [
                            {
                                "cand": [
                                    {"n": "22", "vap": "250"},
                                    {"n": "13", "vap": "650"},
                                ]
                            }
                        ]
                    }
                ],
            }
        ],
        "v": {"tv": "1000", "vb": "40", "tvn": "60"},
    }


class ColetaSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger(f"teste-{self.id()}")
        self.logger.handlers.clear()
        self.logger.addHandler(logging.NullHandler())

    def test_normaliza_e_detecta_totalizacao_final(self) -> None:
        resultado = normalize_second_round("ce", dados_tse(finalizada=True))
        self.assertTrue(resultado["apuracao_finalizada"])
        self.assertEqual(resultado["votos_brancos"], 40)
        self.assertEqual(resultado["votos_nulos"], 60)
        self.assertEqual(resultado["percentual_secoes_totalizadas"], 12.7)

    def test_rejeita_total_inconsistente(self) -> None:
        dados = dados_tse()
        dados["v"]["tv"] = "1001"
        with self.assertRaisesRegex(ValueError, "total inconsistente"):
            normalize_second_round("ce", dados)

    def test_exterior_usa_codigo_zz(self) -> None:
        self.assertTrue(
            tse_url("6258", "exterior").endswith(
                "/zz/zz-c0001-e006258-u.json"
            )
        )

    def test_mock_tem_todas_as_localidades_e_totais_consistentes(self) -> None:
        source = MockSecondRoundSource(
            DEFAULT_MOCK_PATH,
            FIRST_ROUND_TURNOUT_PATH,
        )
        for location in RESULT_LOCATIONS:
            data = source.load(location)
            self.assertEqual(
                data["total_votos_apurados"],
                data["votos_flavio_bolsonaro"]
                + data["votos_lula"]
                + data["votos_brancos"]
                + data["votos_nulos"],
                location,
            )
            self.assertEqual(data["gerado_em_tse"]["id"], "MOCK")

    def test_execucao_mock_nao_instancia_cliente_tse(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            pasta = Path(temporaria)
            options = snapshot.SnapshotOptions(
                output_dir=pasta,
                workers=4,
                attempts=1,
                timeout=1,
                mock=True,
            )
            confirmation = patch.object(
                snapshot, "confirm_result", return_value=True
            )
            with (
                confirmation as confirm,
                patch.object(
                    snapshot,
                    "TSEClient",
                    side_effect=AssertionError("TSE não deve ser acessado"),
                ),
            ):
                code = snapshot.run_snapshot(
                    options,
                    self.logger,
                    datetime(
                        2026, 10, 25, 19, 31, 2,
                        tzinfo=ZoneInfo("America/Sao_Paulo"),
                    ),
                )

            self.assertEqual(code, 0)
            confirm.assert_called_once_with()
            collection_path = pasta / "coleta_mock_20261025_193102.json"
            result_path = pasta / "resultado_mock_20261025_193102.json"
            self.assertTrue(collection_path.exists())
            self.assertTrue(result_path.exists())
            collection = json.loads(collection_path.read_text())
            self.assertEqual(collection["modo"], "mock")
            self.assertEqual(len(collection["estados"]), 28)

    def test_uma_execucao_salva_coleta_e_resultado_com_mesmo_horario(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            pasta = Path(temporaria)
            options = snapshot.SnapshotOptions(
                output_dir=pasta,
                workers=2,
                attempts=1,
                timeout=1,
                assume_yes=True,
            )
            coleta_local = {
                "total_votos_apurados": 100,
                "votos_flavio_bolsonaro": 30,
                "votos_lula": 60,
                "votos_brancos": 4,
                "votos_nulos": 6,
                "apuracao_finalizada": False,
            }
            with (
                patch.object(snapshot, "RESULT_LOCATIONS", ("ac", "exterior")),
                patch.object(
                    snapshot, "collect_location", return_value=coleta_local
                ),
                patch.object(snapshot, "read_json", return_value={"locais": {}}),
                patch.object(
                    snapshot,
                    "project_election",
                    return_value={"resultados": []},
                ),
            ):
                codigo = snapshot.run_snapshot(
                    options,
                    self.logger,
                    datetime(
                        2026, 10, 25, 19, 30, 0,
                        tzinfo=ZoneInfo("America/Sao_Paulo"),
                    ),
                )

            self.assertEqual(codigo, 0)
            coleta = pasta / "coleta_20261025_193000.json"
            resultado = pasta / "resultado_20261025_193000.json"
            self.assertTrue(coleta.exists())
            self.assertTrue(resultado.exists())
            self.assertEqual(json.loads(coleta.read_text())["status"], "completo")

    def test_falha_local_preserva_coleta_incompleta_sem_resultado(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            pasta = Path(temporaria)
            options = snapshot.SnapshotOptions(
                output_dir=pasta,
                workers=2,
                attempts=1,
                timeout=1,
                assume_yes=True,
            )

            def coleta_simulada(local, *_args):
                if local == "exterior":
                    raise RuntimeError("endpoint indisponível")
                return {
                    "total_votos_apurados": 100,
                    "votos_flavio_bolsonaro": 30,
                    "votos_lula": 60,
                    "votos_brancos": 4,
                    "votos_nulos": 6,
                    "apuracao_finalizada": False,
                }

            with (
                patch.object(snapshot, "RESULT_LOCATIONS", ("ac", "exterior")),
                patch.object(
                    snapshot, "collect_location", side_effect=coleta_simulada
                ),
            ):
                codigo = snapshot.run_snapshot(
                    options,
                    self.logger,
                    datetime(
                        2026, 10, 25, 19, 30, 1,
                        tzinfo=ZoneInfo("America/Sao_Paulo"),
                    ),
                )

            coleta = pasta / "coleta_20261025_193001.json"
            resultado = pasta / "resultado_20261025_193001.json"
            salvo = json.loads(coleta.read_text())
            self.assertEqual(codigo, 1)
            self.assertEqual(salvo["status"], "incompleto")
            self.assertEqual(list(salvo["estados"]), ["ac"])
            self.assertIn("exterior", salvo["erros"])
            self.assertFalse(resultado.exists())


if __name__ == "__main__":
    unittest.main()
