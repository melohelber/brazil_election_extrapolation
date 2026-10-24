"""Configuração central do projeto."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
FIRST_ROUND_DIR = DATA_DIR / "primeiro_turno"
FIRST_ROUND_CANDIDATES_DIR = FIRST_ROUND_DIR / "candidatos"
FIRST_ROUND_TURNOUT_PATH = FIRST_ROUND_DIR / "comparecimento.json"
EXAMPLES_DIR = DATA_DIR / "exemplos"
MOCKS_DIR = DATA_DIR / "mocks"
DEFAULT_MOCK_PATH = MOCKS_DIR / "cenario_padrao.json"
RUNTIME_DIR = PROJECT_ROOT / "var"
SNAPSHOTS_DIR = RUNTIME_DIR / "snapshots"
MOCK_SNAPSHOTS_DIR = RUNTIME_DIR / "mock_snapshots"
LOGS_DIR = RUNTIME_DIR / "logs"

FIRST_ROUND_ELECTION = "6257"
SECOND_ROUND_ELECTION = "6258"
PRESIDENT_OFFICE = "0001"

FLAVIO_NUMBER = "22"
LULA_NUMBER = "13"

UFS = (
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go",
    "ma", "mt", "ms", "mg", "pa", "pb", "pr", "pe", "pi",
    "rj", "rn", "rs", "ro", "rr", "sc", "sp", "se", "to",
)
RESULT_LOCATIONS = UFS + ("exterior",)
FIRST_ROUND_LOCATIONS = ("brasil",) + RESULT_LOCATIONS
TSE_CODES = {
    "brasil": "br",
    **{uf: uf for uf in UFS},
    "exterior": "zz",
}

TSE_URL = (
    "https://resultados.tse.jus.br/oficial/ele2026/{election}/dados/"
    "{code}/{code}-c{office}-e00{election}-u.json"
)


def tse_url(election: str, location: str) -> str:
    """Monta a URL oficial do TSE para uma localidade."""

    code = TSE_CODES[location]
    return TSE_URL.format(
        election=election,
        code=code,
        office=PRESIDENT_OFFICE,
    )
