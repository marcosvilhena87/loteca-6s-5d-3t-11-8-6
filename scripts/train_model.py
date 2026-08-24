"""Fit a transparent temperature calibrator to historical probabilities."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from scripts.common import actual_result, log_loss, probabilities, rank_results, rank_scale, read_loteca_csv, temperature_scale, top1_risk_scale
from scripts.preprocess_data import validate_rows


TEMPERATURES = tuple(value / 100 for value in range(50, 201))
MIN_VALIDATION_GAIN = 1e-6
RANK_PRIOR_GAMES = 20.0
RISK_PRIOR_GAMES = 30.0
RISK_STABILITY_WINDOWS = (50, 100, 200)


def _best_temperature(rows: list[dict[str, str]]) -> float:
    """Return the grid temperature with the lowest multiclass log-loss."""
    return min(TEMPERATURES, key=lambda value: log_loss(rows, value))


def _validated_temperature(candidate: float, raw_loss: float, calibrated_loss: float) -> tuple[float, bool]:
    """Promote calibration only when it improves unseen chronological data.

    A temperature fitted in-sample can make the probabilities worse and, in
    turn, make the ticket optimizer confidently choose the wrong allocation.
    Falling back to 1.0 makes that failure mode explicit and deterministic.
    """
    promoted = calibrated_loss + MIN_VALIDATION_GAIN < raw_loss
    return (candidate if promoted else 1.0), promoted


def _rank_lifts(rows: list[dict[str, str]], temperature: float) -> list[float]:
    """Estimate smoothed observed/predicted ratios for Top1, Top2 and Top3."""
    predicted = [0.0, 0.0, 0.0]
    hits = [0.0, 0.0, 0.0]
    for row in rows:
        probs = temperature_scale(probabilities(row), temperature)
        ranking = rank_results(probs)
        for index, result in enumerate(ranking):
            predicted[index] += probs[result]
            hits[index] += actual_result(row) == result
    count = len(rows)
    return [
        (hits[index] + RANK_PRIOR_GAMES * predicted[index] / count)
        / (predicted[index] * (1.0 + RANK_PRIOR_GAMES / count))
        for index in range(3)
    ]


def _calibrated_log_loss(rows: list[dict[str, str]], temperature: float, lifts: list[float]) -> float:
    loss = 0.0
    for row in rows:
        probs = rank_scale(temperature_scale(probabilities(row), temperature), lifts)
        loss -= math.log(max(probs[actual_result(row)], 1e-15))
    return loss / len(rows)


def _risk_rank_observations(
    rows: list[dict[str, str]], temperature: float, rank_lifts: list[float]
) -> list[list[tuple[int, float, int]]]:
    """Return (contest, predicted Top1, hit) observations for each risk rank."""
    observations: list[list[tuple[int, float, int]]] = [[] for _ in range(14)]
    contests: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        contests.setdefault(int(row["Concurso"]), []).append(row)
    for contest_rows in contests.values():
        prepared = []
        for row in contest_rows:
            probs = rank_scale(temperature_scale(probabilities(row), temperature), rank_lifts)
            prepared.append((row, probs, probs[rank_results(probs)[0]]))
        for index, (row, probs, _) in enumerate(sorted(prepared, key=lambda item: (item[2], int(item[0]["Jogo"])))):
            top1 = rank_results(probs)[0]
            observations[index].append((int(row["Concurso"]), probs[top1], int(actual_result(row) == top1)))
    return observations


def _risk_rank_analysis(rows: list[dict[str, str]], temperature: float, rank_lifts: list[float]) -> list[dict]:
    """Audit risk-rank signal and shrink noisy/temporally unstable estimates."""
    analysis = []
    for index, values in enumerate(_risk_rank_observations(rows, temperature, rank_lifts)):
        count = len(values)
        if not count:
            analysis.append({"risk_rank": index + 1, "n_jogos": 0, "lift_shrunk": 1.0, "historical_confidence": 0.0})
            continue
        predicted = sum(value[1] for value in values)
        hits = sum(value[2] for value in values)
        mean_predicted = predicted / count
        hit_rate = hits / count
        # Wilson interval remains meaningful even for small samples.
        z = 1.959963984540054
        denominator = 1.0 + z * z / count
        centre = (hit_rate + z * z / (2 * count)) / denominator
        radius = z * math.sqrt(hit_rate * (1 - hit_rate) / count + z * z / (4 * count * count)) / denominator
        ordered = sorted(values)
        window_rates = {
            str(window): sum(value[2] for value in ordered[-window:]) / min(window, count)
            for window in RISK_STABILITY_WINDOWS if count >= window
        }
        window_rates["all"] = hit_rate
        dispersion = statistics.pstdev(window_rates.values()) if len(window_rates) > 1 else 0.0
        stability = max(0.0, 1.0 - dispersion / 0.10)
        sample_strength = count / (count + RISK_PRIOR_GAMES)
        confidence = sample_strength * stability
        shrunk_hit_rate = mean_predicted + confidence * (hit_rate - mean_predicted)
        lift = shrunk_hit_rate / mean_predicted if mean_predicted else 1.0
        analysis.append({
            "risk_rank": index + 1, "n_jogos": count,
            "pTop1_medio_previsto": mean_predicted, "Top1_hit_observado": hit_rate,
            "Top1_fail_observado": 1.0 - hit_rate,
            "ic95_hit_low": min(hit_rate, max(0.0, centre - radius)),
            "ic95_hit_high": max(hit_rate, min(1.0, centre + radius)), "window_hit_rates": window_rates,
            "risk_rank_stability": stability, "historical_confidence": confidence,
            "confidence_label": "HIGH" if confidence >= 0.75 else ("MEDIUM" if confidence >= 0.45 else "LOW"),
            "lift_raw": hit_rate / mean_predicted if mean_predicted else 1.0, "lift_shrunk": lift,
        })
    return analysis


def _risk_rank_lifts(rows: list[dict[str, str]], temperature: float, rank_lifts: list[float]) -> list[float]:
    """Learn stability- and sample-shrunk Top1 factors by risk rank 1..14."""
    return [item["lift_shrunk"] for item in _risk_rank_analysis(rows, temperature, rank_lifts)]


def _risk_log_loss(rows: list[dict[str, str]], temperature: float, rank_lifts: list[float], risk_lifts: list[float]) -> float:
    loss = 0.0
    contests: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        contests.setdefault(int(row["Concurso"]), []).append(row)
    for contest_rows in contests.values():
        prepared = []
        for row in contest_rows:
            probs = rank_scale(temperature_scale(probabilities(row), temperature), rank_lifts)
            prepared.append((row, probs, probs[rank_results(probs)[0]]))
        for index, (row, probs, _) in enumerate(sorted(prepared, key=lambda item: (item[2], int(item[0]["Jogo"])))):
            calibrated = top1_risk_scale(probs, risk_lifts[index])
            loss -= math.log(max(calibrated[actual_result(row)], 1e-15))
    return loss / len(rows)


def _tail_metrics(base_hits: list[int], challenger_hits: list[int]) -> dict:
    """Summarize paired ticket results with emphasis on the 13+ objective.

    Pairing by contest is important: ``Net13Gain`` is not the difference of
    two unrelated averages, but the balance of contests that actually cross
    the target boundary in either direction.
    """
    if len(base_hits) != len(challenger_hits) or not base_hits:
        raise ValueError("Acertos BASE e challenger devem ter o mesmo tamanho não vazio")
    gains = sum(base < 13 <= challenger for base, challenger in zip(base_hits, challenger_hits))
    losses = sum(challenger < 13 <= base for base, challenger in zip(base_hits, challenger_hits))
    transitions: dict[str, int] = {}
    for base, challenger in zip(base_hits, challenger_hits):
        key = f"{base}->{challenger}"
        transitions[key] = transitions.get(key, 0) + 1
    return {
        "contests": len(base_hits),
        "base_13plus": sum(hits >= 13 for hits in base_hits),
        "challenger_13plus": sum(hits >= 13 for hits in challenger_hits),
        "base_12plus": sum(hits >= 12 for hits in base_hits),
        "challenger_12plus": sum(hits >= 12 for hits in challenger_hits),
        "base_mean_hits": sum(base_hits) / len(base_hits),
        "challenger_mean_hits": sum(challenger_hits) / len(challenger_hits),
        "crossed_to_13plus": gains,
        "fell_below_13": losses,
        "net13_gain": gains - losses,
        "transitions": transitions,
    }


def _decision_impact(contests: list[tuple[list[dict], list[dict], int, int]]) -> dict:
    """Measure whether probability changes reach, and improve, final tickets.

    Calibration metrics alone cannot reveal operational value: a probability
    adjustment may leave every selected mark unchanged.  This paired funnel
    deliberately compares the effective marks (rather than incidental output
    ordering) and reports outcomes only where the challenger intervened.
    """
    changed = []
    ranking_changes = 0
    double_changes = 0
    hit_changes = 0
    tier_changes = 0
    for base, challenger, base_hits, challenger_hits in contests:
        base_by_game = {int(game["Jogo"]): game for game in base}
        challenger_by_game = {int(game["Jogo"]): game for game in challenger}
        if any(
            (base_by_game[game]["top1"], base_by_game[game]["top2"], base_by_game[game]["top3"])
            != (challenger_by_game[game]["top1"], challenger_by_game[game]["top2"], challenger_by_game[game]["top3"])
            for game in base_by_game
        ):
            ranking_changes += 1
        base_doubles = {game for game, item in base_by_game.items() if item["tipo"] == "duplo"}
        challenger_doubles = {game for game, item in challenger_by_game.items() if item["tipo"] == "duplo"}
        if base_doubles != challenger_doubles:
            double_changes += 1
        ticket_changed = any(
            base_by_game[game]["palpite"] != challenger_by_game[game]["palpite"]
            for game in base_by_game
        )
        if ticket_changed:
            changed.append((base_hits, challenger_hits))
        hit_changes += base_hits != challenger_hits
        tier_changes += (base_hits >= 13) != (challenger_hits >= 13)

    total = len(contests)
    wins = sum(challenger > base for base, challenger in changed)
    losses = sum(challenger < base for base, challenger in changed)
    ties = len(changed) - wins - losses
    return {
        "contests_evaluated": total,
        "ranking_changed_contests": ranking_changes,
        "double_set_changed_contests": double_changes,
        "final_ticket_changed_contests": len(changed),
        "hits_changed_contests": hit_changes,
        "13plus_changed_contests": tier_changes,
        "top1_ranking_change_rate": ranking_changes / total if total else 0.0,
        "double_set_change_rate": double_changes / total if total else 0.0,
        "final_ticket_change_rate": len(changed) / total if total else 0.0,
        "n_changed_tickets": len(changed),
        "mean_hits_champion_changed": sum(base for base, _ in changed) / len(changed) if changed else 0.0,
        "mean_hits_challenger_changed": sum(challenger for _, challenger in changed) / len(changed) if changed else 0.0,
        "13plus_champion_changed": sum(base >= 13 for base, _ in changed),
        "13plus_challenger_changed": sum(challenger >= 13 for _, challenger in changed),
        "decision_net_gain": sum(challenger - base for base, challenger in changed),
        "decision_win_rate": wins / len(changed) if changed else 0.0,
        "decision_loss_rate": losses / len(changed) if changed else 0.0,
        "decision_tie_rate": ties / len(changed) if changed else 0.0,
    }


def _ticket_tail_validation(
    rows: list[dict[str, str]], temperature: float, rank_lifts: list[float], risk_lifts: list[float]
) -> dict:
    """Compare BASE and RISK_RANK on real, chronologically held-out contests."""
    # Local import keeps the probability utilities usable without importing
    # the comparatively heavier constrained optimizer during module loading.
    from scripts.predict_results import optimize

    contests: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        contests.setdefault(int(row["Concurso"]), []).append(row)
    base_hits, challenger_hits, paired_contests = [], [], []
    for contest in sorted(contests):
        contest_rows = contests[contest]
        base, _ = optimize(contest_rows, temperature, rank_lifts)
        challenger, _ = optimize(contest_rows, temperature, rank_lifts, risk_lifts)
        results = {int(row["Jogo"]): actual_result(row) for row in contest_rows}
        base_count = sum(results[int(game["Jogo"])] in game["palpite"] for game in base)
        challenger_count = sum(results[int(game["Jogo"])] in game["palpite"] for game in challenger)
        base_hits.append(base_count)
        challenger_hits.append(challenger_count)
        paired_contests.append((base, challenger, base_count, challenger_count))
    metrics = _tail_metrics(base_hits, challenger_hits)
    metrics["decision_impact"] = _decision_impact(paired_contests)
    return metrics


def train(history_path: str | Path, model_path: str | Path) -> dict:
    rows = read_loteca_csv(history_path)
    validate_rows(rows, historical=True)
    contests = sorted({int(row["Concurso"]) for row in rows})
    cutoff = contests[max(1, int(len(contests) * 0.8)) - 1]
    fit_rows = [row for row in rows if int(row["Concurso"]) <= cutoff]
    validation = [row for row in rows if int(row["Concurso"]) > cutoff]
    validation_candidate = _best_temperature(fit_rows)
    raw_loss = log_loss(validation, 1.0)
    temperature_loss = _calibrated_log_loss(validation, validation_candidate, [1.0, 1.0, 1.0])
    candidate_lifts = _rank_lifts(fit_rows, validation_candidate)
    rank_loss = _calibrated_log_loss(validation, validation_candidate, candidate_lifts)
    candidate_loss = min(temperature_loss, rank_loss)
    selected_temperature, promoted = _validated_temperature(validation_candidate, raw_loss, candidate_loss)
    rank_promoted = promoted and rank_loss <= temperature_loss

    validation_rank_lifts = candidate_lifts if rank_promoted else [1.0, 1.0, 1.0]
    candidate_risk_lifts = _risk_rank_lifts(fit_rows, validation_candidate if promoted else 1.0, validation_rank_lifts)
    base_validation_loss = rank_loss if rank_promoted else (temperature_loss if promoted else raw_loss)
    risk_validation_loss = _risk_log_loss(
        validation, validation_candidate if promoted else 1.0, validation_rank_lifts, candidate_risk_lifts
    )
    risk_tail_validation = _ticket_tail_validation(
        validation, validation_candidate if promoted else 1.0, validation_rank_lifts, candidate_risk_lifts
    )
    # A probabilistic gain alone is insufficient.  Never deploy risk_rank when
    # its real held-out tickets lose 13+ contests or have negative Net13Gain.
    risk_promoted = (
        risk_validation_loss + MIN_VALIDATION_GAIN < base_validation_loss
        and risk_tail_validation["challenger_13plus"] >= risk_tail_validation["base_13plus"]
        and risk_tail_validation["net13_gain"] >= 0
        and risk_tail_validation["decision_impact"]["decision_net_gain"] >= 0
    )

    # After the calibration method has passed the chronological gate, refit its
    # sole parameter with every contest available before deployment.  The
    # validation contest outcomes are historical at this point and no future
    # contest information is used.
    temperature = _best_temperature(rows) if promoted else 1.0
    rank_lifts = _rank_lifts(rows, temperature) if rank_promoted else [1.0, 1.0, 1.0]
    risk_rank_lifts = _risk_rank_lifts(rows, temperature, rank_lifts) if risk_promoted else [1.0] * 14
    risk_rank_audit = _risk_rank_analysis(rows, temperature, rank_lifts)
    model = {
        "type": "temperature_scaling",
        "temperature": temperature,
        "calibration_promoted": promoted,
        "rank_calibration_promoted": rank_promoted,
        "rank_lifts": rank_lifts,
        "risk_rank_calibration_promoted": risk_promoted,
        "risk_rank_lifts": risk_rank_lifts,
        "risk_rank_audit": risk_rank_audit,
        "validation_candidate_temperature": validation_candidate,
        "validation_selected_temperature": selected_temperature,
        "training_games": len(fit_rows),
        "validation_games": len(validation),
        "training_last_contest": cutoff,
        "validation_log_loss_raw": raw_loss,
        "validation_log_loss_calibrated": candidate_loss,
        "validation_log_loss_temperature": temperature_loss,
        "validation_log_loss_rank_calibrated": rank_loss,
        "validation_log_loss_before_risk_rank": base_validation_loss,
        "validation_log_loss_risk_rank": risk_validation_loss,
        "risk_rank_tail_validation": risk_tail_validation,
        "deployment_log_loss_all_history": log_loss(rows, temperature),
    }
    destination = Path(model_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return model
