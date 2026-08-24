"""Input validation utilities."""

from __future__ import annotations

from scripts.common import actual_result, probabilities


def validate_rows(rows: list[dict[str, str]], *, historical: bool) -> None:
    if not rows:
        raise ValueError("Arquivo de entrada vazio")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        required = ("Concurso", "Jogo", "Mandante", "Visitante", "p(1)", "p(x)", "p(2)")
        missing = [field for field in required if not row.get(field)]
        if missing:
            raise ValueError(f"Campos ausentes no jogo {row.get('Jogo', '?')}: {', '.join(missing)}")
        key = (row["Concurso"], row["Jogo"])
        if key in seen:
            raise ValueError(f"Jogo duplicado: concurso {key[0]}, jogo {key[1]}")
        seen.add(key)
        probabilities(row)
        if historical:
            actual_result(row)


def validate_next_contest(rows: list[dict[str, str]]) -> None:
    validate_rows(rows, historical=False)
    contests = {row["Concurso"] for row in rows}
    games = sorted(int(row["Jogo"]) for row in rows)
    if len(contests) != 1 or games != list(range(1, 15)):
        raise ValueError("O próximo concurso deve conter exatamente os jogos 1 a 14")
