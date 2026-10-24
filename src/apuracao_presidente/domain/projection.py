"""Regras puras para projetar a apuração presidencial."""

from decimal import Decimal, ROUND_FLOOR
from typing import Any

from apuracao_presidente.config import RESULT_LOCATIONS


VOTE_KEYS = ("flavio_bolsonaro", "lula", "brancos_nulos")
VALID_LOCATIONS = set(RESULT_LOCATIONS)


def percentage(part: int, total: int) -> float:
    return round(100 * part / total, 4) if total else 0.0


def describe_votes(votes: dict[str, int]) -> dict[str, dict[str, int | float]]:
    valid = votes["flavio_bolsonaro"] + votes["lula"]
    total = valid + votes["brancos_nulos"]
    return {
        "flavio_bolsonaro": {
            "percentual_sobre_validos": percentage(
                votes["flavio_bolsonaro"], valid
            ),
            "votos_brutos": votes["flavio_bolsonaro"],
        },
        "lula": {
            "percentual_sobre_validos": percentage(votes["lula"], valid),
            "votos_brutos": votes["lula"],
        },
        "votos_validos": {
            "percentual_sobre_total": percentage(valid, total),
            "votos_brutos": valid,
        },
        "brancos_nulos": {
            "percentual_sobre_total": percentage(votes["brancos_nulos"], total),
            "votos_brutos": votes["brancos_nulos"],
        },
    }


def calculate_factor(
    *,
    first_round_total: int,
    current_total: int,
) -> Decimal:
    """Calcula comparecimento do primeiro turno dividido pelo total atual."""

    if first_round_total <= 0:
        raise ValueError("O total de votos do primeiro turno deve ser positivo")
    if current_total <= 0:
        raise ValueError("O total de votos apurados agora deve ser positivo")
    if current_total >= first_round_total:
        return Decimal(1)
    return Decimal(first_round_total) / Decimal(current_total)


def extrapolate_preserving_total(
    votes: dict[str, int],
    factor: Decimal,
    projected_total: int,
) -> dict[str, int]:
    """Extrapola as categorias e mantém a soma igual ao total projetado."""

    exact = {key: Decimal(votes[key]) * factor for key in VOTE_KEYS}
    rounded = {
        key: int(value.quantize(Decimal("1"), rounding=ROUND_FLOOR))
        for key, value in exact.items()
    }
    missing = projected_total - sum(rounded.values())
    if not 0 <= missing <= len(VOTE_KEYS):
        raise ValueError("O fator de extrapolação não corresponde ao total projetado")
    order = sorted(
        VOTE_KEYS,
        key=lambda key: exact[key] - rounded[key],
        reverse=True,
    )
    for key in order[:missing]:
        rounded[key] += 1
    return rounded


def _read_vote(data: dict[str, Any], primary_key: str, alias: str) -> int:
    value = data.get(primary_key, data.get(alias))
    if value is None:
        raise ValueError(f"Campo obrigatório ausente: {primary_key}")
    return int(value)


def project_location(
    location: str,
    data: dict[str, Any],
    first_round_total: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        current_total = int(data["total_votos_apurados"])
        flavio = _read_vote(
            data, "votos_flavio_bolsonaro", "votos_candidato_a"
        )
        lula = _read_vote(data, "votos_lula", "votos_candidato_b")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Entrada inválida para {location.upper()}: {error}"
        ) from error

    if current_total < 0:
        raise ValueError(
            f"total_votos_apurados de {location.upper()} não pode ser negativo"
        )
    if flavio < 0 or lula < 0:
        raise ValueError(
            f"Votos dos candidatos em {location.upper()} não podem ser negativos"
        )
    if flavio + lula > current_total:
        raise ValueError(
            "Flávio + Lula não pode superar total_votos_apurados em "
            f"{location.upper()}"
        )

    current_votes = {
        "flavio_bolsonaro": flavio,
        "lula": lula,
        "brancos_nulos": current_total - flavio - lula,
    }
    current = {
        "uf": location.upper(),
        "total_votos": current_total,
        "resultado_atual": describe_votes(current_votes),
    }
    basis = {
        "votos_totais_primeiro_turno": first_round_total,
        "votos_apurados": current_total,
    }

    if current_total == 0:
        return current, {
            "uf": location.upper(),
            "base_extrapolacao": basis,
            "fator_extrapolacao": None,
            "total_votos": None,
            "resultado_extrapolado": None,
        }

    finished = data.get("apuracao_finalizada") is True
    if finished or current_total >= first_round_total:
        factor = Decimal(1)
        projected_total = current_total
    else:
        factor = calculate_factor(
            first_round_total=first_round_total,
            current_total=current_total,
        )
        projected_total = first_round_total

    projected_votes = extrapolate_preserving_total(
        current_votes,
        factor,
        projected_total,
    )
    projected = {
        "uf": location.upper(),
        "base_extrapolacao": basis,
        "fator_extrapolacao": float(factor),
        "total_votos": projected_total,
        "resultado_extrapolado": describe_votes(projected_votes),
    }
    return current, projected


def _sum_locations(
    locations: dict[str, dict[str, Any]],
    result_type: str,
) -> dict[str, int]:
    totals = {key: 0 for key in VOTE_KEYS}
    result_key = (
        "resultado_atual"
        if result_type == "atual"
        else "resultado_extrapolado"
    )
    for location in locations.values():
        for key in VOTE_KEYS:
            totals[key] += int(location[result_key][key]["votos_brutos"])
    return totals


def _aggregate_brazil(
    locations: dict[str, dict[str, Any]],
    result_type: str,
) -> dict[str, Any]:
    if result_type == "projetado":
        unavailable = sorted(
            location
            for location, result in locations.items()
            if result["resultado_extrapolado"] is None
        )
        if unavailable:
            return {
                "uf": "BRASIL",
                "total_votos": None,
                "resultado_extrapolado": None,
                "localidades_sem_projecao": unavailable,
            }

    votes = _sum_locations(locations, result_type)
    result_key = (
        "resultado_atual"
        if result_type == "atual"
        else "resultado_extrapolado"
    )
    return {
        "uf": "BRASIL",
        "total_votos": sum(votes.values()),
        result_key: describe_votes(votes),
    }


def project_election(
    input_data: dict[str, Any],
    first_round_reference: dict[str, Any],
    *,
    require_all: bool = True,
) -> dict[str, Any]:
    """Projeta todas as localidades e agrega o Brasil ao final."""

    input_locations = input_data.get("estados")
    if not isinstance(input_locations, dict) or not input_locations:
        raise ValueError("A entrada deve conter um objeto não vazio chamado 'estados'")

    normalized = {
        str(location).lower(): data
        for location, data in input_locations.items()
    }
    received = set(normalized)
    invalid = sorted(received - VALID_LOCATIONS)
    if invalid:
        raise ValueError(f"UFs inválidas: {', '.join(invalid)}")

    missing = sorted(set(RESULT_LOCATIONS) - received)
    if require_all and missing:
        raise ValueError(f"Faltam localidades na entrada: {', '.join(missing)}")

    reference_locations = first_round_reference.get("locais")
    if not isinstance(reference_locations, dict):
        raise ValueError("A referência do primeiro turno não contém 'locais'")

    current_results: dict[str, dict[str, Any]] = {}
    projected_results: dict[str, dict[str, Any]] = {}
    ordered_locations = [
        location for location in RESULT_LOCATIONS if location in received
    ]

    for location in ordered_locations:
        data = normalized[location]
        if not isinstance(data, dict):
            raise ValueError(
                f"Os dados de {location.upper()} devem ser um objeto JSON"
            )
        reference = reference_locations.get(location)
        if not isinstance(reference, dict):
            raise ValueError(
                f"Referência do primeiro turno ausente para {location.upper()}"
            )
        try:
            first_round_total = int(reference["total_votos_primeiro_turno"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Comparecimento do primeiro turno inválido para "
                f"{location.upper()}"
            ) from error

        current, projected = project_location(
            location,
            data,
            first_round_total,
        )
        current_results[location.upper()] = current
        projected_results[location.upper()] = projected

    results = [
        {
            "local": location.upper(),
            "votos_totais_primeiro_turno": projected_results[
                location.upper()
            ]["base_extrapolacao"]["votos_totais_primeiro_turno"],
            "atual": current_results[location.upper()],
            "projetado": projected_results[location.upper()],
        }
        for location in ordered_locations
    ]
    results.append(
        {
            "local": "BRASIL",
            "votos_totais_primeiro_turno": sum(
                projected_results[location.upper()]["base_extrapolacao"][
                    "votos_totais_primeiro_turno"
                ]
                for location in ordered_locations
            ),
            "atual": _aggregate_brazil(current_results, "atual"),
            "projetado": _aggregate_brazil(projected_results, "projetado"),
        }
    )
    return {"resultados": results}
