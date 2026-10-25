#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from apuracao_presidente.domain.projection import (
    calculate_factor,
    project_election,
    project_location,
)
from apuracao_presidente.infrastructure.storage import write_json_atomic


class ProjecaoTest(unittest.TestCase):
    def test_extrapola_candidatos_e_invalidos(self) -> None:
        atual, projetado = project_location(
            "ce",
            {
                "total_votos_apurados": 1_000_000,
                "votos_flavio_bolsonaro": 250_000,
                "votos_lula": 650_000,
            },
            10_000_000,
        )

        self.assertEqual(
            atual["resultado_atual"]["brancos_nulos"]["votos_brutos"],
            100_000,
        )
        self.assertEqual(atual["uf"], "CE")
        self.assertEqual(projetado["uf"], "CE")
        self.assertEqual(
            atual["resultado_atual"]["votos_validos"]["votos_brutos"],
            900_000,
        )
        self.assertEqual(projetado["total_votos"], 10_000_000)
        self.assertEqual(
            projetado["resultado_extrapolado"]["lula"]["votos_brutos"],
            6_500_000,
        )
        self.assertEqual(
            projetado["resultado_extrapolado"]["brancos_nulos"]["votos_brutos"],
            1_000_000,
        )
        self.assertEqual(
            projetado["resultado_extrapolado"]["flavio_bolsonaro"][
                "percentual_sobre_validos"
            ],
            27.7778,
        )
        self.assertEqual(
            projetado["resultado_extrapolado"]["flavio_bolsonaro"]["votos_brutos"],
            2_500_000,
        )

    def test_brancos_e_nulos_ficam_fora_do_percentual_valido(self) -> None:
        atual, _ = project_location(
            "sp",
            {
                "total_votos_apurados": 1_000,
                "votos_flavio_bolsonaro": 360,
                "votos_lula": 540,
            },
            2_000,
        )
        self.assertEqual(
            atual["resultado_atual"]["brancos_nulos"]["percentual_sobre_total"],
            10.0,
        )
        self.assertEqual(
            atual["resultado_atual"]["flavio_bolsonaro"][
                "percentual_sobre_validos"
            ],
            40.0,
        )
        self.assertEqual(
            atual["resultado_atual"]["lula"]["percentual_sobre_validos"],
            60.0,
        )

    def test_agrega_brasil_com_votos_projetados(self) -> None:
        resultado = project_election(
            {
                "estados": {
                    "ce": {
                        "total_votos_apurados": 1_000,
                        "votos_flavio_bolsonaro": 250,
                        "votos_lula": 650,
                    },
                    "sp": {
                        "total_votos_apurados": 2_000,
                        "votos_flavio_bolsonaro": 900,
                        "votos_lula": 900,
                    },
                }
            },
            {
                "locais": {
                    "ce": {"total_votos_primeiro_turno": 10_000},
                    "sp": {"total_votos_primeiro_turno": 10_000},
                }
            },
            require_all=False,
        )
        brasil = resultado["resultados"][-1]["projetado"]
        self.assertEqual(
            brasil["resultado_extrapolado"]["flavio_bolsonaro"]["votos_brutos"],
            7_000,
        )
        self.assertEqual(
            brasil["resultado_extrapolado"]["lula"]["votos_brutos"], 11_000
        )
        self.assertEqual(
            brasil["resultado_extrapolado"]["brancos_nulos"]["votos_brutos"],
            2_000,
        )
        self.assertEqual(brasil["total_votos"], 20_000)
        self.assertEqual(
            brasil["resultado_extrapolado"]["flavio_bolsonaro"][
                "percentual_sobre_validos"
            ],
            38.8889,
        )

    def test_exige_todas_as_ufs_por_padrao(self) -> None:
        with self.assertRaisesRegex(ValueError, "Faltam localidades"):
            project_election(
                {
                    "estados": {
                        "ce": {
                            "total_votos_apurados": 100,
                            "votos_flavio_bolsonaro": 30,
                            "votos_lula": 60,
                        }
                    }
                },
                {"locais": {}},
            )

    def test_salva_um_unico_json_com_estados_e_brasil_no_final(self) -> None:
        resultado = project_election(
            {
                "estados": {
                    "ce": {
                        "total_votos_apurados": 100,
                        "votos_flavio_bolsonaro": 30,
                        "votos_lula": 60,
                    }
                }
            },
            {"locais": {"ce": {"total_votos_primeiro_turno": 1_000}}},
            require_all=False,
        )
        with tempfile.TemporaryDirectory() as temporaria:
            pasta = Path(temporaria)
            caminho = pasta / "resultado.json"
            write_json_atomic(resultado, caminho)
            self.assertEqual(list(pasta.iterdir()), [caminho])
            salvo = json.loads(caminho.read_text())
            self.assertEqual(set(salvo), {"resultados"})
            self.assertEqual(salvo["resultados"][0]["local"], "CE")
            self.assertEqual(
                salvo["resultados"][0]["votos_totais_primeiro_turno"], 1_000
            )
            self.assertEqual(salvo["resultados"][-1]["local"], "BRASIL")
            self.assertEqual(
                salvo["resultados"][-1]["votos_totais_primeiro_turno"], 1_000
            )
            self.assertEqual(
                set(salvo["resultados"][-1]["projetado"]),
                {"uf", "total_votos", "resultado_extrapolado"},
            )
            self.assertEqual(
                salvo["resultados"][-1]["projetado"]["uf"], "BRASIL"
            )

    def test_base_e_fator_de_extrapolacao(self) -> None:
        _, projetado = project_location(
            "ce",
            {
                "total_votos_apurados": 1_000,
                "votos_flavio_bolsonaro": 300,
                "votos_lula": 600,
            },
            10_000,
        )
        self.assertEqual(
            projetado["base_extrapolacao"],
            {
                "votos_totais_primeiro_turno": 10_000,
                "votos_apurados": 1_000,
            },
        )
        self.assertEqual(projetado["fator_extrapolacao"], 10.0)

    def test_apuracao_finalizada_nao_extrapola(self) -> None:
        atual, projetado = project_location(
            "ce",
            {
                "total_votos_apurados": 1_000,
                "votos_flavio_bolsonaro": 300,
                "votos_lula": 600,
                "apuracao_finalizada": True,
            },
            10_000,
        )
        self.assertEqual(projetado["fator_extrapolacao"], 1.0)
        self.assertEqual(projetado["total_votos"], 1_000)
        self.assertEqual(
            projetado["resultado_extrapolado"], atual["resultado_atual"]
        )

    def test_comparecimento_superior_ao_primeiro_turno_nao_reduz_votos(self) -> None:
        _, projetado = project_location(
            "ce",
            {
                "total_votos_apurados": 11_000,
                "votos_flavio_bolsonaro": 5_000,
                "votos_lula": 5_000,
            },
            10_000,
        )
        self.assertEqual(projetado["fator_extrapolacao"], 1.0)
        self.assertEqual(projetado["total_votos"], 11_000)

    def test_fator_isolado_tambem_nao_reduz_comparecimento_atual(self) -> None:
        self.assertEqual(
            calculate_factor(
                first_round_total=10_000,
                current_total=11_000,
            ),
            1,
        )

    def test_localidade_sem_votos_redistribui_validos_do_primeiro_turno(self) -> None:
        atual, projetado = project_location(
            "ac",
            {
                "total_votos_apurados": 0,
                "votos_flavio_bolsonaro": 0,
                "votos_lula": 0,
            },
            1_000,
            first_round_data={
                "votos_validos_primeiro_turno": 900,
                "brancos_primeiro_turno": 40,
                "nulos_primeiro_turno": 60,
                "votos_flavio_bolsonaro_primeiro_turno": 300,
                "votos_lula_primeiro_turno": 200,
            },
        )
        self.assertEqual(atual["total_votos"], 0)
        self.assertIsNone(projetado["fator_extrapolacao"])
        self.assertEqual(
            projetado["origem_projecao"],
            "primeiro_turno_redistribuido",
        )
        self.assertEqual(projetado["total_votos"], 1_000)
        self.assertEqual(
            projetado["resultado_extrapolado"]["flavio_bolsonaro"]["votos_brutos"],
            540,
        )
        self.assertEqual(
            projetado["resultado_extrapolado"]["lula"]["votos_brutos"],
            360,
        )
        self.assertEqual(
            projetado["resultado_extrapolado"]["brancos_nulos"]["votos_brutos"],
            100,
        )

    def test_primeiro_turno_nao_altera_localidade_com_votos_atuais(self) -> None:
        _, projetado = project_location(
            "ac",
            {
                "total_votos_apurados": 100,
                "votos_flavio_bolsonaro": 20,
                "votos_lula": 70,
            },
            1_000,
            first_round_data={
                "votos_validos_primeiro_turno": 900,
                "brancos_primeiro_turno": 40,
                "nulos_primeiro_turno": 60,
                "votos_flavio_bolsonaro_primeiro_turno": 800,
                "votos_lula_primeiro_turno": 100,
            },
        )
        self.assertEqual(projetado["origem_projecao"], "apuracao_segundo_turno")
        self.assertEqual(
            projetado["resultado_extrapolado"]["flavio_bolsonaro"]["votos_brutos"],
            200,
        )
        self.assertEqual(
            projetado["resultado_extrapolado"]["lula"]["votos_brutos"],
            700,
        )

    def test_exterior_e_incluido_no_brasil(self) -> None:
        resultado = project_election(
            {
                "estados": {
                    "ce": {
                        "total_votos_apurados": 100,
                        "votos_flavio_bolsonaro": 30,
                        "votos_lula": 60,
                    },
                    "exterior": {
                        "total_votos_apurados": 50,
                        "votos_flavio_bolsonaro": 10,
                        "votos_lula": 35,
                    },
                }
            },
            {
                "locais": {
                    "ce": {"total_votos_primeiro_turno": 1_000},
                    "exterior": {"total_votos_primeiro_turno": 500},
                }
            },
            require_all=False,
        )
        self.assertEqual(
            [item["local"] for item in resultado["resultados"]],
            ["CE", "EXTERIOR", "BRASIL"],
        )
        self.assertEqual(
            resultado["resultados"][-1]["votos_totais_primeiro_turno"],
            1_500,
        )


if __name__ == "__main__":
    unittest.main()
