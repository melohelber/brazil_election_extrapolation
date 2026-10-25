"""Fonte local e determinística para simular a coleta do segundo turno."""

from pathlib import Path
from typing import Any

from apuracao_presidente.config import RESULT_LOCATIONS
from apuracao_presidente.infrastructure.storage import read_json


class MockSecondRoundSource:
    """Converte um cenário simples no mesmo formato produzido pelo TSE."""

    def __init__(self, scenario_path: Path, first_round_path: Path) -> None:
        scenario = read_json(scenario_path)
        reference = read_json(first_round_path)
        self.scenario_path = scenario_path
        self.states = scenario.get("estados")
        self.reference = reference.get("locais")
        self.default_sections_percentage = scenario.get(
            "percentual_secoes_totalizadas_padrao"
        )

        if not isinstance(self.states, dict):
            raise ValueError("O mock deve conter um objeto chamado 'estados'")
        if not isinstance(self.reference, dict):
            raise ValueError("A referência deve conter um objeto chamado 'locais'")

        received = set(self.states)
        expected = set(RESULT_LOCATIONS)
        missing = sorted(expected - received)
        invalid = sorted(received - expected)
        if missing:
            raise ValueError(
                "Faltam localidades no mock: " + ", ".join(missing)
            )
        if invalid:
            raise ValueError(
                "Localidades inválidas no mock: " + ", ".join(invalid)
            )

    def load(self, location: str) -> dict[str, Any]:
        data = self.states[location]
        if not isinstance(data, dict):
            raise ValueError(f"Mock de {location.upper()} deve ser um objeto")

        try:
            total = int(data["total_votos_apurados"])
            flavio = int(data["votos_flavio_bolsonaro"])
            lula = int(data["votos_lula"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Mock inválido para {location.upper()}: {error}"
            ) from error

        if min(total, flavio, lula) < 0:
            raise ValueError(
                f"Mock de {location.upper()} possui votos negativos"
            )
        blank_and_null = total - flavio - lula
        if blank_and_null < 0:
            raise ValueError(
                f"Flávio + Lula supera o total no mock de {location.upper()}"
            )

        first_round = self.reference.get(location)
        if not isinstance(first_round, dict):
            raise ValueError(
                f"Referência ausente para {location.upper()}"
            )
        first_blank = int(first_round["brancos_primeiro_turno"])
        first_null = int(first_round["nulos_primeiro_turno"])
        first_invalid = first_blank + first_null
        blank = (
            blank_and_null * first_blank // first_invalid
            if first_invalid
            else 0
        )
        null = blank_and_null - blank

        finished = data.get("apuracao_finalizada", False)
        if not isinstance(finished, bool):
            raise ValueError(
                f"apuracao_finalizada de {location.upper()} deve ser booleano"
            )
        sections_percentage_raw = data.get(
            "percentual_secoes_totalizadas",
            self.default_sections_percentage,
        )
        sections_percentage = (
            float(sections_percentage_raw)
            if sections_percentage_raw is not None
            else None
        )
        if sections_percentage is not None and not 0 <= sections_percentage <= 100:
            raise ValueError(
                f"Percentual de seções inválido no mock de {location.upper()}"
            )

        return {
            "total_votos_apurados": total,
            "votos_flavio_bolsonaro": flavio,
            "votos_lula": lula,
            "votos_brancos": blank,
            "votos_nulos": null,
            "percentual_secoes_totalizadas": sections_percentage,
            "apuracao_finalizada": finished,
            "gerado_em_tse": {
                "data": None,
                "hora": None,
                "id": "MOCK",
            },
        }
