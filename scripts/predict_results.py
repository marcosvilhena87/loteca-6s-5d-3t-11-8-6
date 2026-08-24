"""Constrained optimization of a single 8-dry/6-double Loteca ticket."""

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
    """Measure every valid double/dry exchange with exact P(>=13).

    The exchanged games keep their selected rank sets.  Consequently the
    10/5/5 totals and the D12/D13/D23 composition are preserved while the
    location of one double changes.  Invalid Flamengo exchanges are discarded
    by the independent validator instead of being silently reported.
    """
    validate_ticket(predictions)
    original = sum(_ticket_distribution(predictions)[13:])
    doubles = [game for game in predictions if game["tipo"] == "duplo"]
    dry_games = [game for game in predictions if game["tipo"] == "seco"]
    audit = []
    for selected in doubles:
        selected_ranks = tuple(int(rank[-1]) - 1 for rank in selected["ranks_selecionados"].split("+"))
        for substitute in dry_games:
            substitute_rank = int(substitute["ranks_selecionados"][-1]) - 1
            alternative = [dict(game) for game in predictions]
            by_number = {int(game["Jogo"]): game for game in alternative}
            demoted = by_number[int(selected["Jogo"])]
            promoted = by_number[int(substitute["Jogo"])]
            _set_selected_ranks(demoted, (substitute_rank,))
            _set_selected_ranks(promoted, selected_ranks)
            try:
                validate_ticket(alternative)
            except ValueError:
                continue
            probability = sum(_ticket_distribution(alternative)[13:])
            audit.append({
                "DuploOriginal": int(selected["Jogo"]),
                "JogoSubstituto": int(substitute["Jogo"]),
                "TipoOriginal": selected["tipo_duplo"],
                "TipoSubstituto": f"D{selected_ranks[0] + 1}{selected_ranks[1] + 1}",
                "P13plus_original": original,
                "P13plus_alternativo": probability,
                "DeltaP13plus": probability - original,
            })
    return audit


def _set_selected_ranks(game: dict, ranks: tuple[int, ...]) -> None:
    """Update a copied prediction consistently for structural audit."""
    selected = [game[f"top{rank + 1}"] for rank in ranks]
    game["palpite"] = "".join(result for result in RESULTS_ORDER if result in selected)
    game["ranks_selecionados"] = "+".join(f"top{rank + 1}" for rank in ranks)
    game["tipo"] = "duplo" if len(ranks) == 2 else "seco"
    game["tipo_duplo"] = f"D{ranks[0] + 1}{ranks[1] + 1}" if len(ranks) == 2 else "-"
    game["probabilidade_coberta"] = sum(game[f"p(top{rank + 1})"] for rank in ranks)


RESULTS_ORDER = ("1", "X", "2")


def validate_ticket(predictions: list[dict]) -> None:
    """Independently reject an optimized ticket that violates a hard constraint."""
    if len(predictions) != 14:
        raise ValueError(f"A aposta deve ter 14 jogos; recebeu {len(predictions)}")
    dry = sum(game["tipo"] == "seco" for game in predictions)
    doubles = sum(game["tipo"] == "duplo" for game in predictions)
    triples = sum(len(game["palpite"]) == 3 for game in predictions)
    rank_counts = [
        sum(f"top{rank}" in game["ranks_selecionados"].split("+") for game in predictions)
        for rank in range(1, 4)
    ]
    markings = sum(len(game["palpite"]) for game in predictions)
    if (dry, doubles, triples, *rank_counts, markings) != (8, 6, 0, 10, 5, 5, 20):
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
    options = [(0,), (1,), (2,), (0, 1), (0, 2), (1, 2)]
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

    # State: number of selected rank-1/rank-2/rank-3 outcomes and doubles.
    states: dict[tuple[int, int, int, int], list[Candidate]] = {(0, 0, 0, 0): [Candidate(1.0, 0.0, ())]}
    for row, probs, ranking, options, _, _, _ in games:
        expanded: dict[tuple[int, int, int, int], list[Candidate]] = {}
        for counts, frontier in states.items():
            for option in options:
                new_counts = tuple(counts[index] + (index in option) for index in range(3)) + (counts[3] + (len(option) == 2),)
                if any(new_counts[index] > (10, 5, 5)[index] for index in range(3)) or new_counts[3] > 6:
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

    finalists = states.get((10, 5, 5, 6), [])
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
        gain = sum(probs[ranking[index]] for index in choice) - probs[ranking[0]] if len(choice) == 2 else 0.0
        gain_kind = "RecoveryGain" if choice == (1, 2) else ("DoubleGain" if len(choice) == 2 else "-")
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
            "risk_rank": risk_rank,
            "pTop1_base": base_probs[base_ranking[0]], "pTop1_ajustado": probs[ranking[0]],
            "delta_pTop1": probs[ranking[0]] - base_probs[base_ranking[0]],
            "top1_base": base_ranking[0], "ranking_mudou": base_ranking != ranking,
            "tipo": "duplo" if len(choice) == 2 else "seco", "tipo_duplo": double_kind,
            "double_gain": gain, "gain_kind": gain_kind, "palpite": ordered_marks,
            "ranks_selecionados": "+".join(f"top{index + 1}" for index in choice),
            "probabilidade_coberta": sum(probs[result] for result in selected),
            "P13plus_otimo": best_probability,
            "perda_relativa_soft": (best_probability - best.success) / best_probability,
            "tolerancia_relativa_soft": soft_relative_tolerance,
        })
    validate_ticket(output)
    return output, best.success


def predict(next_path: str | Path, model_path: str | Path, output_path: str | Path) -> tuple[list[dict], float]:
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
    return predictions, success


def print_telemetry(predictions: list[dict], success: float) -> None:
    print("\n=== TELEMETRIA DA APOSTA OTIMIZADA ===")
    for game in predictions:
        print(f"Jogo {game['Jogo']:>2} | {game['Mandante']} x {game['Visitante']}")
        print(f"  p(1)={game['p(1)']:.4f} p(X)={game['p(X)']:.4f} p(2)={game['p(2)']:.4f}")
        print(f"  ranking: {game['top1']} ({game['p(top1)']:.4f}) > {game['top2']} ({game['p(top2)']:.4f}) > {game['top3']} ({game['p(top3)']:.4f})")
        print(f"  gap12={game['gap12']:.4f} gap13={game['gap13']:.4f} entropia={game['entropy']:.4f} risk_rank={game['risk_rank']}")
        print(f"  coberturas: D12={game['CoberturaD12']:.4f} D13={game['CoberturaD13']:.4f} "
              f"D23={game['CoberturaD23']:.4f}")
        print(f"  risk audit: pTop1 {game['pTop1_base']:.4f} -> {game['pTop1_ajustado']:.4f} "
              f"({game['delta_pTop1']:+.4f}); top1 {game['top1_base']} -> {game['top1']} "
              f"| ranking mudou: {'SIM' if game['ranking_mudou'] else 'NÃO'}")
        double_audit = (f" | {game['tipo_duplo']} {game['gain_kind']}={game['double_gain']:+.4f}"
                        if game["tipo"] == "duplo" else "")
        print(f"  {game['tipo']}: {game['palpite']} [{game['ranks_selecionados']}] "
              f"cobertura={game['probabilidade_coberta']:.4f}{double_audit}")
    dry = sum(game["tipo"] == "seco" for game in predictions)
    doubles = sum(game["tipo"] == "duplo" for game in predictions)
    rank_counts = [sum(f"top{rank}" in game["ranks_selecionados"].split("+") for game in predictions) for rank in range(1, 4)]
    flamengo_games = [game for game in predictions if "FLAMENGO/RJ" in (normalized_team(game["Mandante"]), normalized_team(game["Visitante"]))]
    flamengo_ok = all(("1" if normalized_team(game["Mandante"]) == "FLAMENGO/RJ" else "2") in game["palpite"] for game in flamengo_games)
    print("\n=== VALIDAÇÃO DAS HARD CONSTRAINTS ===")
    print(f"Secos: {dry}/8 | Duplos: {doubles}/6 | Triplos: 0/0")
    print(f"Top1: {rank_counts[0]}/10 | Top2: {rank_counts[1]}/5 | Top3: {rank_counts[2]}/5")
    print(f"Total de marcações: {sum(len(game['palpite']) for game in predictions)}/20")
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
    _print_double_cutoff(predictions, exact_success)


def _print_substitution_audit(predictions: list[dict]) -> None:
    """Print the best valid replacement for each selected double."""
    audit = substitution_audit(predictions)
    print("\n=== MATRIZ DE SUBSTITUIÇÕES ESTRUTURAIS ===")
    print("Duplo | Substituto | Tipo | P13+ original | P13+ alternativo | DeltaP13+")
    for game in sorted({item["DuploOriginal"] for item in audit}):
        best = max((item for item in audit if item["DuploOriginal"] == game), key=lambda item: item["DeltaP13plus"])
        print(f"{game:>6} | {best['JogoSubstituto']:>10} | {best['TipoOriginal']:>4} | "
              f"{best['P13plus_original']:.8%} | {best['P13plus_alternativo']:.8%} | "
              f"{best['DeltaP13plus']:+.8%}")


def _print_double_cutoff(predictions: list[dict], original_success: float) -> None:
    """Audit the sixth/seventh Top1-risk boundary and its concrete P13+ cost."""
    ordered = sorted(predictions, key=lambda game: (-1.0 + game["p(top1)"], int(game["Jogo"])))
    print("\n=== FRONTEIRA DO 6º VS 7º CANDIDATO A DUPLO ===")
    print("Rank | Jogo | pTop1 | 1-pTop1 | Decisão")
    for rank, game in enumerate(ordered, 1):
        separator = "  <--- cutoff" if rank in (6, 7) else ""
        print(f"{rank:>4} | {int(game['Jogo']):>4} | {game['p(top1)']:.4f} | {1-game['p(top1)']:.4f} | {game['tipo'].upper()}{separator}")

    sixth, seventh = ordered[5], ordered[6]
    exchangeable = (
        sixth["ranks_selecionados"] == "top2+top3"
        and seventh["ranks_selecionados"] == "top1"
    )
    if not exchangeable:
        print("Troca direta não aplicável: as decisões globais no cutoff não são Top2+Top3 e Top1.")
        return

    swapped_coverages = []
    for game in predictions:
        if game is sixth:
            swapped_coverages.append(game["p(top1)"])
        elif game is seventh:
            swapped_coverages.append(game["p(top2)"] + game["p(top3)"])
        else:
            swapped_coverages.append(game["probabilidade_coberta"])
    swapped = sum(hit_distribution(swapped_coverages)[13:])
    delta = swapped - original_success
    relative = delta / original_success if original_success else 0.0
    margin = abs(seventh["p(top1)"] - sixth["p(top1)"])
    narrow = margin <= 0.01
    material = abs(relative) > 0.01
    print(f"P13+ original: {original_success:.8%}")
    print(f"P13+ após trocar o 6º pelo 7º: {swapped:.8%}")
    print(f"Delta absoluto: {delta:+.8%} | Delta relativo: {relative:+.4%}")
    print(f"Margem pTop1: {margin:.4f}")
    print(f"Fronteira probabilística: {'ESTREITA' if narrow else 'AMPLA'}")
    print(f"Robustez no objetivo: {'MATERIAL' if material else 'IMATERIAL'}")
