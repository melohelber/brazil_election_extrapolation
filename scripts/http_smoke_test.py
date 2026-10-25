"""Smoke test HTTP do fluxo frontend -> coleta -> projeção."""

import argparse
import json
from urllib.request import Request, urlopen


def get_json(url: str) -> dict:
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    with urlopen(f"{base_url}/", timeout=10) as response:
        html = response.read().decode("utf-8")
    if "Radar Eleitoral 2026" not in html or "Atualizar apuração" not in html:
        raise RuntimeError("O frontend esperado não foi servido")

    health = get_json(f"{base_url}/api/snapshot?health=1")
    journal_run = get_json(f"{base_url}/api/cron?mock=1")
    history = get_json(f"{base_url}/api/history?mock=1")["historico"]
    collection = get_json(f"{base_url}/api/snapshot?mock=1")["coleta"]
    request = Request(
        f"{base_url}/api/snapshot",
        data=json.dumps({"coleta": collection}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)["resultado"]
    brazil = result["resultados"][-1]

    report = {
        "frontend": "ok",
        "api": health["status"],
        "diario": journal_run["status"],
        "rodadas_no_historico": history["total"],
        "coleta": collection["status"],
        "localidades": len(collection["estados"]),
        "ultimo_resultado": brazil["local"],
        "projecao_brasil": (
            "disponivel"
            if brazil["projetado"]["resultado_extrapolado"] is not None
            else "indisponivel"
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
