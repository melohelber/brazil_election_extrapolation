#!/usr/bin/env python3

import unittest

from apuracao_presidente.application.first_round import load_projection_reference
from apuracao_presidente.config import (
    FIRST_ROUND_CANDIDATES_DIR,
    FIRST_ROUND_LOCATIONS,
    FIRST_ROUND_TURNOUT_PATH,
    RESULT_LOCATIONS,
)
from apuracao_presidente.infrastructure.storage import read_json


class BasePrimeiroTurnoTest(unittest.TestCase):
    def test_possui_brasil_27_ufs_e_exterior(self) -> None:
        arquivos = {
            arquivo.stem
            for arquivo in FIRST_ROUND_CANDIDATES_DIR.glob("*.json")
        }
        self.assertEqual(arquivos, set(FIRST_ROUND_LOCATIONS))
        self.assertEqual(len(arquivos), 29)

    def test_candidatos_batem_com_votos_validos_da_referencia(self) -> None:
        referencia = read_json(FIRST_ROUND_TURNOUT_PATH)
        self.assertEqual(set(referencia["locais"]), set(RESULT_LOCATIONS))

        for local in RESULT_LOCATIONS:
            candidatos = read_json(
                FIRST_ROUND_CANDIDATES_DIR / f"{local}.json"
            )
            self.assertGreater(len(candidatos), 0, local)
            self.assertTrue(
                all(set(candidato) == {"nome", "votos"} for candidato in candidatos),
                local,
            )
            self.assertEqual(
                sum(candidato["votos"] for candidato in candidatos),
                referencia["locais"][local]["votos_validos_primeiro_turno"],
                local,
            )

    def test_brasil_e_soma_das_localidades(self) -> None:
        candidatos_brasil = read_json(
            FIRST_ROUND_CANDIDATES_DIR / "brasil.json"
        )
        referencia = read_json(FIRST_ROUND_TURNOUT_PATH)
        self.assertEqual(
            sum(candidato["votos"] for candidato in candidatos_brasil),
            sum(
                dados["votos_validos_primeiro_turno"]
                for dados in referencia["locais"].values()
            ),
        )

    def test_referencia_de_projecao_inclui_flavio_e_lula_por_localidade(self) -> None:
        referencia = load_projection_reference()
        for local in RESULT_LOCATIONS:
            dados = referencia["locais"][local]
            self.assertGreater(
                dados["votos_flavio_bolsonaro_primeiro_turno"],
                0,
                local,
            )
            self.assertGreater(
                dados["votos_lula_primeiro_turno"],
                0,
                local,
            )
            self.assertLessEqual(
                dados["votos_flavio_bolsonaro_primeiro_turno"]
                + dados["votos_lula_primeiro_turno"],
                dados["votos_validos_primeiro_turno"],
                local,
            )


if __name__ == "__main__":
    unittest.main()
