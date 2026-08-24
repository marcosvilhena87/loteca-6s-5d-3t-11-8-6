"""Constrained optimization of a single 6-dry/5-double/3-triple ticket."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from scripts.common import normalized_team, probabilities, rank_results, rank_scale, read_loteca_csv, temperature_scale, top1_risk_scale
from scripts.preprocess_data import validate_next_contest


@dataclass(frozen=True)
class Candidate:
    p0: float
    p1: float
    choices: tuple[tuple[int, ...], ...]
    avoided_teams: int = 0

    @property
    def success(self) -> float:
        return self.p0 + self.p1


def hit_distribution(coverages: list[float]) -> list[float]:
    """Return exact probabilities for 0..N correct games.

    Each game's ``coverage`` is the probability that its selected mark (or one
    of its two marks) is correct.  The convolution avoids Monte Carlo noise and
    makes the optimized objective independently auditable.
    """
    distribution = [1.0]
    for coverage in coverages:
        updated = [0.0] * (len(distribution) + 1)
        for hits, probability in enumerate(distribution):
            updated[hits] += probability * (1.0 - coverage)
            updated[hits + 1] += probability * coverage
        distribution = updated
    return distribution


def _ticket_distribution(predictions: list[dict]) -> list[float]:
    return hit_distribution([game["probabilidade_coberta"] for game in predictions])


def substitution_audit(predictions: list[dict]) -> list[dict]:
    """Measure every valid pairwise structural exchange exactly.

    Swapping the complete rank decisions of two games covers both native
    boundaries (triple/double and double/dry), as well as changes between rank
    compositions such as D12/D23.  Counts, rank totals and markings remain
    invariant by construction.  The independent validator still rejects a
    swap that would remove Flamengo's mandatory victory.
    """
    validate_ticket(predictions)
    original_distribution = _ticket_distribution(predictions)
    original_14 = original_distribution[14]
    original_13 = sum(original_distribution[13:])
    original_12 = sum(original_distribution[12:])
    audit = []
    for index, selected in enumerate(predictions):
        selected_ranks = _selected_ranks(selected)
        for substitute in predictions[index + 1:]:
            substitute_ranks = _selected_ranks(substitute)
            if selected_ranks == substitute_ranks:
                continue
            alternative = [dict(game) for game in predictions]
            by_number = {int(game["Jogo"]): game for game in alternative}
            _set_selected_ranks(by_number[int(selected["Jogo"])], substitute_ranks)
            _set_selected_ranks(by_number[int(substitute["Jogo"])], selected_ranks)
            try:
                validate_ticket(alternative)
            except ValueError:
                continue
            distribution = _ticket_distribution(alternative)
            alternative_14 = distribution[14]
            alternative_13 = sum(distribution[13:])
            alternative_12 = sum(distribution[12:])
            for source, target in ((selected, substitute), (substitute, selected)):
                audit.append({
                    "JogoOriginal": int(source["Jogo"]),
                    "JogoSubstituto": int(target["Jogo"]),
                    "DecisaoAtual": source["tipo_estrutural"],
                    "Alternativa": target["tipo_estrutural"],
                    "P14_original": original_14,
                    "P14_alternativo": alternative_14,
                    "DeltaP14": alternative_14 - original_14,
                    "P13plus_original": original_13,
                    "P13plus_alternativo": alternative_13,
                    "DeltaP13plus": alternative_13 - original_13,
                    "P12plus_original": original_12,
                    "P12plus_alternativo": alternative_12,
                    "DeltaP12plus": alternative_12 - original_12,
                })
    return audit


def _selected_ranks(game: dict) -> tuple[int, ...]:
    return tuple(int(rank[-1]) - 1 for rank in game["ranks_selecionados"].split("+"))


def add_structural_telemetry(predictions: list[dict]) -> list[dict]:
    """Add structural margins and their diagnostic classification per game."""
    audit = substitution_audit(predictions)
    alternatives_by_game = {
        game: sorted(
            (item for item in audit if item["JogoOriginal"] == game),
            key=lambda item: (-item["P13plus_alternativo"], item["JogoSubstituto"]),
        )
        for game in {int(item["Jogo"]) for item in predictions}
    }
    best_by_game = {game: alternatives[0] for game, alternatives in alternatives_by_game.items()}
    importance = {
        game: item["P13plus_original"] - item["P13plus_alternativo"]
        for game, item in best_by_game.items()
    }
    ranks = {
        game: rank for rank, game in enumerate(
            sorted(importance, key=lambda number: (-importance[number], number)), 1
        )
    }
    for game in predictions:
        number = int(game["Jogo"])
        alternative = best_by_game[number]
        second = alternatives_by_game[number][1] if len(alternatives_by_game[number]) > 1 else alternative
        game["StructuralMargin"] = importance[number]
        game["RelativeStructuralMargin"] = (
            importance[number] / alternative["P13plus_original"]
            if alternative["P13plus_original"] else 0.0
        )
        game["StructuralClass"] = structural_margin_class(importance[number])
        game["BestAlternativeMargin"] = importance[number]
        game["SecondBestMargin"] = alternative["P13plus_original"] - second["P13plus_alternativo"]
        game["AlternativeGap"] = game["SecondBestMargin"] - game["StructuralMargin"]
        game["structural_rank"] = ranks[number]
        game["melhor_alternativa_valida"] = (
            f"J{alternative['JogoSubstituto']}:{alternative['Alternativa']}"
        )
        game["DeltaP13plus_alternativa"] = alternative["DeltaP13plus"]
        game["DeltaP12plus_alternativa"] = alternative["DeltaP12plus"]
    margins = sorted(importance.values())
    mean = sum(margins) / len(margins)
    median = (margins[len(margins) // 2 - 1] + margins[len(margins) // 2]) / 2
    deviation = math.sqrt(sum((margin - mean) ** 2 for margin in margins) / len(margins))
    for game in predictions:
        game["TicketRigidityIndex"] = mean
        game["StructuralMarginMedian"] = median
        game["StructuralMarginMin"] = margins[0]
        game["StructuralMarginMax"] = margins[-1]
        game["StructuralMarginStdDev"] = deviation
    return predictions


def structural_margin_class(margin: float) -> str:
    """Classify an absolute P(13+) margin using README percentage-point bands."""
    if margin < 0.00075:
        return "MARGINAL"
    if margin < 0.002:
        return "MODERADA"
    if margin < 0.004:
        return "FORTE"
    return "MUITO FORTE"


def write_substitution_audit(predictions: list[dict], output_path: str | Path) -> Path:
    """Persist the complete valid structural substitution matrix as CSV."""
    rows = substitution_audit(predictions)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    contest = predictions[0]["Concurso"] if predictions else ""
    serialized = [{
        "Concurso": contest,
        "JogoOriginal": row["JogoOriginal"],
        "DecisaoOriginal": row["DecisaoAtual"],
        "JogoSubstituto": row["JogoSubstituto"],
        "DecisaoAlternativa": row["Alternativa"],
        "P14_original": row["P14_original"],
        "P14_alternativo": row["P14_alternativo"],
        "DeltaP14": row["DeltaP14"],
        "P13plus_original": row["P13plus_original"],
        "P13plus_alternativo": row["P13plus_alternativo"],
        "DeltaP13plus": row["DeltaP13plus"],
        "P12plus_original": row["P12plus_original"],
        "P12plus_alternativo": row["P12plus_alternativo"],
        "DeltaP12plus": row["DeltaP12plus"],
    } for row in rows]
    if not serialized:
        raise ValueError("A matriz de substituições estruturais está vazia")
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(serialized[0]), delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(serialized)
    return destination


def _set_selected_ranks(game: dict, ranks: tuple[int, ...]) -> None:
    """Update a copied prediction consistently for structural audit."""
    selected = [game[f"top{rank + 1}"] for rank in ranks]
    game["palpite"] = "".join(result for result in RESULTS_ORDER if result in selected)
    game["ranks_selecionados"] = "+".join(f"top{rank + 1}" for rank in ranks)
    game["tipo"] = {1: "seco", 2: "duplo", 3: "triplo"}[len(ranks)]
    game["tipo_duplo"] = f"D{ranks[0] + 1}{ranks[1] + 1}" if len(ranks) == 2 else "-"
    game["tipo_estrutural"] = game["tipo_duplo"] if len(ranks) == 2 else ("T123" if len(ranks) == 3 else f"S{ranks[0] + 1}")
    game["probabilidade_coberta"] = sum(game[f"p(top{rank + 1})"] for rank in ranks)


RESULTS_ORDER = ("1", "X", "2")


def validate_ticket(predictions: list[dict]) -> None:
    """Independently reject an optimized ticket that violates a hard constraint."""
    if len(predictions) != 14:
        raise ValueError(f"A aposta deve ter 14 jogos; recebeu {len(predictions)}")
    dry = sum(game["tipo"] == "seco" for game in predictions)
    doubles = sum(game["tipo"] == "duplo" for game in predictions)
    triples = sum(game["tipo"] == "triplo" for game in predictions)
    rank_counts = [
        sum(f"top{rank}" in game["ranks_selecionados"].split("+") for game in predictions)
        for rank in range(1, 4)
    ]
    markings = sum(len(game["palpite"]) for game in predictions)
    if (dry, doubles, triples, *rank_counts, markings) != (6, 5, 3, 11, 8, 6, 25):
        raise ValueError(
            "Hard Constraints violadas: "
            f"secos={dry}, duplos={doubles}, triplos={triples}, "
            f"Top1/2/3={rank_counts}, marcações={markings}"
        )
    for game in predictions:
        home, away = normalized_team(game["Mandante"]), normalized_team(game["Visitante"])
        if "FLAMENGO/RJ" in (home, away):
            victory = "1" if home == "FLAMENGO/RJ" else "2"
            if victory not in game["palpite"]:
                raise ValueError(f"Vitória do Flamengo ausente no jogo {game['Jogo']}")


def _pareto(candidates: list[Candidate]) -> list[Candidate]:
    result: list[Candidate] = []
    # A probabilistically dominated partial ticket may still be the documented
    # soft-constraint winner inside the near-optimal band.  Preserve one Pareto
    # frontier for every anti-Palmeiras/Vasco mask so that optimization cannot
    # discard that preference before the final objective is known.
    for mask in range(4):
        ordered = sorted(
            (item for item in candidates if item.avoided_teams == mask),
            key=lambda item: (-item.p0, -item.p1),
        )
        best_p1 = -1.0
        for candidate in ordered:
            if candidate.p1 > best_p1 + 1e-18:
                result.append(candidate)
                best_p1 = candidate.p1
    return result


def _avoided_team_mask(row: dict[str, str], ranking: tuple[str, str, str], option: tuple[int, ...]) -> int:
    """Return bits for preferred teams whose victory is absent from a choice."""
    home, away = normalized_team(row["Mandante"]), normalized_team(row["Visitante"])
    mask = 0
    for bit, team in enumerate(("PALMEIRAS/SP", "VASCO DA GAMA/RJ")):
        if team in (home, away):
            victory = "1" if home == team else "2"
            if ranking.index(victory) not in option:
                mask |= 1 << bit
    return mask


def _allowed_options(row: dict[str, str], ranking: tuple[str, str, str]) -> list[tuple[int, ...]]:
    options = [(0,), (1,), (2,), (0, 1), (0, 2), (1, 2), (0, 1, 2)]
    home, away = normalized_team(row["Mandante"]), normalized_team(row["Visitante"])
    if "FLAMENGO/RJ" in (home, away):
        victory = "1" if home == "FLAMENGO/RJ" else "2"
        options = [option for option in options if ranking.index(victory) in option]
    return options


def optimize(
    rows: list[dict[str, str]], temperature: float, rank_lifts: list[float] | tuple[float, ...] = (1.0, 1.0, 1.0),
    risk_rank_lifts: list[float] | tuple[float, ...] = (1.0,) * 14,
    soft_relative_tolerance: float = 0.005,
) -> tuple[list[dict], float]:
    validate_next_contest(rows)
    if len(risk_rank_lifts) != 14:
        raise ValueError("risk_rank_lifts deve conter 14 fatores")
    if not 0.0 <= soft_relative_tolerance < 1.0:
        raise ValueError("soft_relative_tolerance deve estar no intervalo [0, 1)")
    games = []
    prepared = []
    for row in rows:
        probs = rank_scale(temperature_scale(probabilities(row), temperature), rank_lifts)
        prepared.append((row, probs, probs[rank_results(probs)[0]]))
    risk_rank_by_game = {
        int(row["Jogo"]): index + 1
        for index, (row, _, _) in enumerate(sorted(prepared, key=lambda item: (item[2], int(item[0]["Jogo"]))))
    }
    for row, probs, _ in sorted(prepared, key=lambda item: int(item[0]["Jogo"])):
        risk_rank = risk_rank_by_game[int(row["Jogo"])]
        base_probs = probs
        base_ranking = rank_results(base_probs)
        probs = top1_risk_scale(probs, risk_rank_lifts[risk_rank - 1])
        ranking = rank_results(probs)
        games.append((row, probs, ranking, _allowed_options(row, ranking), risk_rank, base_probs, base_ranking))

    # State: selected rank-1/rank-2/rank-3 outcomes, doubles and triples.
    states: dict[tuple[int, int, int, int, int], list[Candidate]] = {(0, 0, 0, 0, 0): [Candidate(1.0, 0.0, ())]}
    for row, probs, ranking, options, _, _, _ in games:
        expanded: dict[tuple[int, int, int, int, int], list[Candidate]] = {}
        for counts, frontier in states.items():
            for option in options:
                new_counts = tuple(counts[index] + (index in option) for index in range(3)) + (
                    counts[3] + (len(option) == 2), counts[4] + (len(option) == 3)
                )
                if (any(new_counts[index] > (11, 8, 6)[index] for index in range(3))
                        or new_counts[3] > 5 or new_counts[4] > 3):
                    continue
                coverage = sum(probs[ranking[index]] for index in option)
                bucket = expanded.setdefault(new_counts, [])
                for candidate in frontier:
                    bucket.append(Candidate(
                        candidate.p0 * coverage,
                        candidate.p1 * coverage + candidate.p0 * (1 - coverage),
                        candidate.choices + (option,),
                        candidate.avoided_teams | _avoided_team_mask(row, ranking, option),
                    ))
        states = {state: _pareto(frontier) for state, frontier in expanded.items()}

    finalists = states.get((11, 8, 6, 5, 3), [])
    if not finalists:
        raise RuntimeError("Não existe aposta que satisfaça todas as Hard Constraints")

    def soft_score(candidate: Candidate) -> tuple[int, int, int, int]:
        """Apply the documented preferences only between objective ties.

        Runs are evaluated over the game order (not risk order): a longer,
        less fragmented Top1 sequence is preferred after the Palmeiras rule.
        None of these criteria can trade away P(>=13).
        """
        top1_flags = [0 in choice for choice in candidate.choices]
        top1_first_ten = sum(top1_flags[:10])
        runs, longest_run, current_run = 0, 0, 0
        for selected in top1_flags:
            if selected:
                current_run += 1
                longest_run = max(longest_run, current_run)
                if current_run == 1:
                    runs += 1
            else:
                current_run = 0
        return candidate.avoided_teams.bit_count(), top1_first_ten, longest_run, -runs

    best_probability = max(candidate.success for candidate in finalists)
    minimum_probability = best_probability * (1.0 - soft_relative_tolerance)
    near_optimal = [candidate for candidate in finalists if candidate.success + 1e-18 >= minimum_probability]
    best = max(near_optimal, key=lambda candidate: (*soft_score(candidate), candidate.success))

    output = []
    for (row, probs, ranking, _, risk_rank, base_probs, base_ranking), choice in zip(games, best.choices):
        selected = [ranking[index] for index in choice]
        ordered_marks = "".join(result for result in ("1", "X", "2") if result in selected)
        double_kind = f"D{choice[0] + 1}{choice[1] + 1}" if len(choice) == 2 else "-"
        kind = {1: "seco", 2: "duplo", 3: "triplo"}[len(choice)]
        structural_kind = double_kind if len(choice) == 2 else ("T123" if len(choice) == 3 else f"S{choice[0] + 1}")
        gain = sum(probs[ranking[index]] for index in choice) - probs[ranking[0]] if len(choice) > 1 else 0.0
        gain_kind = ("TripleGain" if len(choice) == 3 else
                     "RecoveryGain" if choice == (1, 2) else "DoubleGain" if len(choice) == 2 else "-")
        output.append({
            "Concurso": row["Concurso"], "Jogo": row["Jogo"], "Mandante": row["Mandante"], "Visitante": row["Visitante"],
            "p(1)": probs["1"], "p(X)": probs["X"], "p(2)": probs["2"],
            "top1": ranking[0], "top2": ranking[1], "top3": ranking[2],
            "p(top1)": probs[ranking[0]], "p(top2)": probs[ranking[1]], "p(top3)": probs[ranking[2]],
            "gap12": probs[ranking[0]] - probs[ranking[1]],
            "gap13": probs[ranking[0]] - probs[ranking[2]],
            "entropy": -sum(probability * math.log(probability) for probability in probs.values()),
            "CoberturaD12": probs[ranking[0]] + probs[ranking[1]],
            "CoberturaD13": probs[ranking[0]] + probs[ranking[2]],
            "CoberturaD23": probs[ranking[1]] + probs[ranking[2]],
            "CoberturaT123": 1.0,
            "risk_rank": risk_rank,
            "pTop1_base": base_probs[base_ranking[0]], "pTop1_ajustado": probs[ranking[0]],
            "delta_pTop1": probs[ranking[0]] - base_probs[base_ranking[0]],
            "top1_base": base_ranking[0], "ranking_mudou": base_ranking != ranking,
            "tipo": kind, "tipo_duplo": double_kind, "tipo_estrutural": structural_kind,
            "double_gain": gain if len(choice) == 2 else 0.0,
            "structural_gain": gain, "gain_kind": gain_kind,
            "gain_per_extra_mark": gain / (len(choice) - 1) if len(choice) > 1 else 0.0,
            "palpite": ordered_marks,
            "ranks_selecionados": "+".join(f"top{index + 1}" for index in choice),
            "probabilidade_coberta": sum(probs[result] for result in selected),
            "P13plus_otimo": best_probability,
            "perda_relativa_soft": (best_probability - best.success) / best_probability,
            "tolerancia_relativa_soft": soft_relative_tolerance,
        })
    validate_ticket(output)
    add_structural_telemetry(output)
    return output, best.success


def predict(
    next_path: str | Path,
    model_path: str | Path,
    output_path: str | Path,
    audit_path: str | Path | None = None,
) -> tuple[list[dict], float]:
    model = json.loads(Path(model_path).read_text(encoding="utf-8"))
    predictions, success = optimize(
        read_loteca_csv(next_path), float(model["temperature"]), model.get("rank_lifts", [1.0, 1.0, 1.0]),
        model.get("risk_rank_lifts", [1.0] * 14),
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(predictions[0]), delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(predictions)
    write_substitution_audit(
        predictions,
        audit_path or destination.with_name(f"{destination.stem}_substitutions.csv"),
    )
    return predictions, success


def print_telemetry(predictions: list[dict], success: float) -> None:
    print("\n=== TELEMETRIA DA APOSTA OTIMIZADA ===")
    for game in predictions:
        print(f"Jogo {game['Jogo']:>2} | {game['Mandante']} x {game['Visitante']}")
        print(f"  p(1)={game['p(1)']:.4f} p(X)={game['p(X)']:.4f} p(2)={game['p(2)']:.4f}")
        print(f"  ranking: {game['top1']} ({game['p(top1)']:.4f}) > {game['top2']} ({game['p(top2)']:.4f}) > {game['top3']} ({game['p(top3)']:.4f})")
        print(f"  gap12={game['gap12']:.4f} gap13={game['gap13']:.4f} entropia={game['entropy']:.4f} risk_rank={game['risk_rank']}")
        print(f"  coberturas: D12={game['CoberturaD12']:.4f} D13={game['CoberturaD13']:.4f} "
              f"D23={game['CoberturaD23']:.4f} T123={game['CoberturaT123']:.4f}")
        print(f"  risk audit: pTop1 {game['pTop1_base']:.4f} -> {game['pTop1_ajustado']:.4f} "
              f"({game['delta_pTop1']:+.4f}); top1 {game['top1_base']} -> {game['top1']} "
              f"| ranking mudou: {'SIM' if game['ranking_mudou'] else 'NÃO'}")
        double_audit = (f" | {game['tipo_estrutural']} {game['gain_kind']}={game['structural_gain']:+.4f} "
                        f"por marca extra={game['gain_per_extra_mark']:+.4f}"
                        if game["tipo"] != "seco" else "")
        print(f"  {game['tipo']}: {game['palpite']} [{game['ranks_selecionados']}] "
              f"cobertura={game['probabilidade_coberta']:.4f}{double_audit}")
        print(f"  structural_rank={game['structural_rank']} | StructuralMargin="
              f"{game['StructuralMargin']:.8%} ({game['StructuralClass']}) | relativa="
              f"{game['RelativeStructuralMargin']:.4%} | melhor alternativa: "
              f"{game['melhor_alternativa_valida']} | SecondBestMargin={game['SecondBestMargin']:.8%} "
              f"| AlternativeGap={game['AlternativeGap']:.8%}")
    dry = sum(game["tipo"] == "seco" for game in predictions)
    doubles = sum(game["tipo"] == "duplo" for game in predictions)
    triples = sum(game["tipo"] == "triplo" for game in predictions)
    rank_counts = [sum(f"top{rank}" in game["ranks_selecionados"].split("+") for game in predictions) for rank in range(1, 4)]
    flamengo_games = [game for game in predictions if "FLAMENGO/RJ" in (normalized_team(game["Mandante"]), normalized_team(game["Visitante"]))]
    flamengo_ok = all(("1" if normalized_team(game["Mandante"]) == "FLAMENGO/RJ" else "2") in game["palpite"] for game in flamengo_games)
    print("\n=== VALIDAÇÃO DAS HARD CONSTRAINTS ===")
    print(f"Secos: {dry}/6 | Duplos: {doubles}/5 | Triplos: {triples}/3")
    print(f"Top1: {rank_counts[0]}/11 | Top2: {rank_counts[1]}/8 | Top3: {rank_counts[2]}/6")
    print(f"Total de marcações: {sum(len(game['palpite']) for game in predictions)}/25")
    print(f"Flamengo/RJ: {'regra satisfeita' if flamengo_ok else 'REGRA VIOLADA'}")
    composition = {
        kind: sum(game["tipo_duplo"] == kind for game in predictions)
        for kind in ("D12", "D13", "D23")
    }
    print(f"Composição dos duplos: D12={composition['D12']} | D13={composition['D13']} | D23={composition['D23']}")
    distribution = _ticket_distribution(predictions)
    exact_success = distribution[13] + distribution[14]
    print("\n=== DECOMPOSIÇÃO DO OBJETIVO ===")
    print(f"P(14): {distribution[14]:.8%}")
    print(f"P(13): {distribution[13]:.8%}")
    print(f"P(>=13): {exact_success:.8%}")
    print(f"P(12): {distribution[12]:.8%}")
    print(f"P(>=12): {sum(distribution[12:]):.8%}")
    print(f"Auditoria DP vs otimizador: diferença={abs(exact_success - success):.3e}")
    print("Soft constraints: "
          f"ótimo global={predictions[0]['P13plus_otimo']:.8%} | "
          f"perda relativa={predictions[0]['perda_relativa_soft']:.6%} | "
          f"tolerância={predictions[0]['tolerancia_relativa_soft']:.3%}")
    _print_substitution_audit(predictions)
    _print_structural_summaries(predictions)


def _print_structural_summaries(predictions: list[dict], limit: int = 5) -> None:
    """Print compact views of the rigid core and near-tie zone."""
    ordered = sorted(predictions, key=lambda game: game["structural_rank"])
    print("\n=== NÚCLEO ESTRUTURAL ===")
    print("Rank | Jogo | Decisão | StructuralMargin | Classe")
    for game in ordered[:limit]:
        print(f"{game['structural_rank']:>4} | {int(game['Jogo']):>4} | "
              f"{game['tipo_estrutural']:>7} | {game['StructuralMargin']:.8%} | {game['StructuralClass']}")
    print("\n=== ZONA MARGINAL ===")
    print("Jogo | Decisão | Melhor alternativa | StructuralMargin | DeltaP12+")
    for game in reversed(ordered[-limit:]):
        print(f"{int(game['Jogo']):>4} | {game['tipo_estrutural']:>7} | "
              f"{game['melhor_alternativa_valida']:>18} | {game['StructuralMargin']:.8%} | "
              f"{game['DeltaP12plus_alternativa']:+.8%}")

    margins = [game["StructuralMargin"] for game in predictions]
    classes = {
        name: sum(game["StructuralClass"] == name for game in predictions)
        for name in ("MARGINAL", "MODERADA", "FORTE", "MUITO FORTE")
    }
    print("\n=== PERFIL DE RIGIDEZ ===")
    print(f"MARGINAL={classes['MARGINAL']} | MODERADA={classes['MODERADA']} | "
          f"FORTE={classes['FORTE']} | MUITO FORTE={classes['MUITO FORTE']}")
    print(f"TicketRigidityIndex={predictions[0]['TicketRigidityIndex']:.8%} | "
          f"mediana={predictions[0]['StructuralMarginMedian']:.8%} | "
          f"mínimo={predictions[0]['StructuralMarginMin']:.8%} | "
          f"máximo={predictions[0]['StructuralMarginMax']:.8%} | "
          f"desvio-padrão={predictions[0]['StructuralMarginStdDev']:.8%}")

    highest_risk = min(predictions, key=lambda game: game["risk_rank"])
    lowest_risk = max(predictions, key=lambda game: game["risk_rank"])
    largest_divergence = max(
        predictions,
        key=lambda game: (abs(game["risk_rank"] - game["structural_rank"]), -int(game["Jogo"])),
    )
    print("\n=== DIVERGÊNCIAS RISCO X ESTRUTURA ===")
    print(f"Maior risco: J{highest_risk['Jogo']} | risk_rank={highest_risk['risk_rank']} | "
          f"structural_rank={highest_risk['structural_rank']}")
    print(f"Menor risco: J{lowest_risk['Jogo']} | risk_rank={lowest_risk['risk_rank']} | "
          f"structural_rank={lowest_risk['structural_rank']}")
    print(f"Maior divergência: J{largest_divergence['Jogo']} | risk_rank={largest_divergence['risk_rank']} | "
          f"structural_rank={largest_divergence['structural_rank']} | "
          f"diferença={abs(largest_divergence['risk_rank'] - largest_divergence['structural_rank'])}")


def _print_substitution_audit(predictions: list[dict]) -> None:
    """Print the best valid replacement for each selected double or triple."""
    audit = substitution_audit(predictions)
    print("\n=== MATRIZ DE SUBSTITUIÇÕES ESTRUTURAIS ===")
    print("Original | Substituto | Atual->Alternativa | DeltaP14 | DeltaP13+ | DeltaP12+")
    for game in sorted({item["JogoOriginal"] for item in audit}):
        best = max((item for item in audit if item["JogoOriginal"] == game), key=lambda item: item["DeltaP13plus"])
        print(f"{game:>6} | {best['JogoSubstituto']:>10} | "
              f"{best['DecisaoAtual']:>4}->{best['Alternativa']:<4} | "
              f"{best['DeltaP14']:+.8%} | {best['DeltaP13plus']:+.8%} | {best['DeltaP12plus']:+.8%}")
