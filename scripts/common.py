"""Shared data and probability helpers for the Loteca pipeline."""

from __future__ import annotations

import csv
import math
import unicodedata
from pathlib import Path

RESULTS = ("1", "X", "2")
TIE_PRIORITY = {"1": 0, "2": 1, "X": 2}


def read_loteca_csv(path: str | Path) -> list[dict[str, str]]:
    """Read the repository's semicolon/decimal-comma, Latin-1 CSV files."""
    with Path(path).open(encoding="latin-1", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def decimal(value: str) -> float:
    return float(value.replace(",", "."))


def probabilities(row: dict[str, str]) -> dict[str, float]:
    values = {"1": decimal(row["p(1)"]), "X": decimal(row["p(x)"]), "2": decimal(row["p(2)"])}
    total = sum(values.values())
    if total <= 0 or any(value < 0 for value in values.values()):
        raise ValueError(f"Probabilidades inválidas no jogo {row.get('Jogo', '?')}")
    return {result: value / total for result, value in values.items()}


def rank_results(probs: dict[str, float]) -> tuple[str, str, str]:
    """Rank using the mandatory 1 > 2 > X tie breaker."""
    return tuple(sorted(RESULTS, key=lambda result: (-probs[result], TIE_PRIORITY[result])))


def temperature_scale(probs: dict[str, float], temperature: float) -> dict[str, float]:
    powered = {key: max(value, 1e-15) ** (1.0 / temperature) for key, value in probs.items()}
    total = sum(powered.values())
    return {key: value / total for key, value in powered.items()}


def rank_scale(probs: dict[str, float], lifts: list[float] | tuple[float, ...]) -> dict[str, float]:
    """Apply historical calibration factors by predicted rank and renormalize.

    The rank is determined before applying the factors.  This makes the learned
    correction independent of concrete labels (1/X/2), while the returned
    probabilities are free to form a new, properly auditable ranking.
    """
    if len(lifts) != 3 or any(not math.isfinite(value) or value <= 0 for value in lifts):
        raise ValueError("rank_lifts deve conter três fatores positivos")
    ranking = rank_results(probs)
    scaled = {result: probs[result] * lifts[index] for index, result in enumerate(ranking)}
    total = sum(scaled.values())
    return {result: value / total for result, value in scaled.items()}


def top1_risk_scale(probs: dict[str, float], lift: float) -> dict[str, float]:
    """Calibrate Top1 for a contest-relative risk rank and preserve the remainder.

    ``lift`` is an observed/predicted ratio learned only from older contests.
    Scaling the two other outcomes together preserves their relative evidence;
    normalization keeps the result a valid probability distribution.
    """
    if not math.isfinite(lift) or lift <= 0:
        raise ValueError("risk lift deve ser positivo")
    top1 = rank_results(probs)[0]
    scaled = dict(probs)
    scaled[top1] *= lift
    total = sum(scaled.values())
    return {result: value / total for result, value in scaled.items()}


def actual_result(row: dict[str, str]) -> str:
    hits = [result for result in RESULTS if row.get(result) == "1"]
    if len(hits) != 1:
        raise ValueError(f"Resultado real deve ser one-hot no jogo {row.get('Jogo', '?')}")
    return hits[0]


def normalized_team(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper().strip()


def log_loss(rows: list[dict[str, str]], temperature: float) -> float:
    if not rows:
        return math.nan
    loss = 0.0
    for row in rows:
        calibrated = temperature_scale(probabilities(row), temperature)
        loss -= math.log(max(calibrated[actual_result(row)], 1e-15))
    return loss / len(rows)
