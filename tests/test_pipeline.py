import unittest

from scripts.common import rank_results, rank_scale, top1_risk_scale
from scripts.predict_results import hit_distribution, optimize, substitution_audit, validate_ticket
from scripts.train_model import _decision_impact, _risk_rank_analysis, _tail_metrics, _validated_temperature


class PipelineTests(unittest.TestCase):
    def test_hit_distribution_is_exact_and_normalized(self):
        distribution = hit_distribution([0.5, 0.25])
        self.assertEqual(distribution, [0.375, 0.5, 0.125])
        self.assertAlmostEqual(sum(distribution), 1.0)

    def test_calibration_is_only_promoted_after_out_of_sample_gain(self):
        self.assertEqual(_validated_temperature(0.8, 0.95, 0.94), (0.8, True))
        self.assertEqual(_validated_temperature(0.8, 0.95, 0.96), (1.0, False))
        self.assertEqual(_validated_temperature(0.8, 0.95, 0.95), (1.0, False))

    def test_mandatory_tie_break(self):
        self.assertEqual(rank_results({"1": 0.4, "X": 0.3, "2": 0.3}), ("1", "2", "X"))

    def test_rank_calibration_is_normalized_and_can_correct_order(self):
        calibrated = rank_scale({"1": 0.5, "X": 0.3, "2": 0.2}, [0.5, 1.5, 1.0])
        self.assertAlmostEqual(sum(calibrated.values()), 1.0)
        self.assertEqual(rank_results(calibrated)[0], "X")

    def test_rank_calibration_rejects_invalid_factors(self):
        with self.assertRaisesRegex(ValueError, "três fatores positivos"):
            rank_scale({"1": 0.5, "X": 0.3, "2": 0.2}, [1.0, 0.0, 1.0])

    def test_risk_rank_calibration_preserves_distribution(self):
        calibrated = top1_risk_scale({"1": 0.5, "X": 0.3, "2": 0.2}, 0.5)
        self.assertAlmostEqual(sum(calibrated.values()), 1.0)
        self.assertAlmostEqual(calibrated["X"] / calibrated["2"], 1.5)
        self.assertLess(calibrated["1"], 0.5)

    def test_risk_rank_analysis_reports_confidence_and_wilson_interval(self):
        rows = []
        for contest in range(1, 61):
            for game in range(1, 15):
                rows.append({
                    "Concurso": str(contest), "Jogo": str(game),
                    "Mandante": f"TIME {game} A", "Visitante": f"TIME {game} B",
                    "p(1)": f"0,{50 + game:02d}", "p(x)": "0,25", "p(2)": f"0,{25 - game:02d}",
                    "1": "1", "X": "0", "2": "0",
                })
        audit = _risk_rank_analysis(rows, 1.0, [1.0, 1.0, 1.0])
        self.assertEqual(len(audit), 14)
        self.assertEqual(audit[0]["n_jogos"], 60)
        self.assertLessEqual(audit[0]["ic95_hit_low"], audit[0]["Top1_hit_observado"])
        self.assertGreaterEqual(audit[0]["ic95_hit_high"], audit[0]["Top1_hit_observado"])
        self.assertIn("50", audit[0]["window_hit_rates"])
        self.assertIn(audit[0]["confidence_label"], ("LOW", "MEDIUM", "HIGH"))

    def test_tail_metrics_use_paired_net13_migrations(self):
        metrics = _tail_metrics([12, 13, 14, 11], [13, 12, 14, 13])
        self.assertEqual(metrics["base_13plus"], 2)
        self.assertEqual(metrics["challenger_13plus"], 3)
        self.assertEqual(metrics["crossed_to_13plus"], 2)
        self.assertEqual(metrics["fell_below_13"], 1)
        self.assertEqual(metrics["net13_gain"], 1)
        self.assertEqual(metrics["transitions"]["12->13"], 1)

    def test_tail_metrics_reject_unpaired_results(self):
        with self.assertRaisesRegex(ValueError, "mesmo tamanho"):
            _tail_metrics([12], [])

    def test_decision_impact_counts_only_effective_ticket_changes(self):
        def ticket(mark: str, kind: str = "seco", ranking=("1", "X", "2")):
            return [{
                "Jogo": "1", "palpite": mark, "tipo": kind,
                "top1": ranking[0], "top2": ranking[1], "top3": ranking[2],
            }]

        metrics = _decision_impact([
            (ticket("1"), ticket("1"), 12, 12),
            (ticket("1"), ticket("1X", "duplo"), 12, 13),
            (ticket("1"), ticket("2", ranking=("2", "X", "1")), 13, 11),
        ])
        self.assertEqual(metrics["final_ticket_changed_contests"], 2)
        self.assertEqual(metrics["double_set_changed_contests"], 1)
        self.assertEqual(metrics["ranking_changed_contests"], 1)
        self.assertEqual(metrics["13plus_changed_contests"], 2)
        self.assertEqual(metrics["decision_net_gain"], -1)
        self.assertAlmostEqual(metrics["decision_win_rate"], 0.5)
        self.assertAlmostEqual(metrics["decision_loss_rate"], 0.5)

    def test_optimizer_enforces_all_hard_constraints(self):
        rows = []
        for game in range(1, 15):
            rows.append({
                "Concurso": "1", "Jogo": str(game),
                "Mandante": ("FLAMENGO/RJ" if game == 1 else
                              "PALMEIRAS/SP" if game == 2 else
                              "VASCO DA GAMA/RJ" if game == 3 else f"TIME {game} A"),
                "Visitante": f"TIME {game} B", "p(1)": "0,50", "p(x)": "0,30", "p(2)": "0,20",
            })
        predictions, probability = optimize(rows, 1.0)
        self.assertGreater(probability, 0)
        self.assertEqual(sum(item["tipo"] == "seco" for item in predictions), 6)
        self.assertEqual(sum(item["tipo"] == "duplo" for item in predictions), 5)
        self.assertEqual(sum(item["tipo"] == "triplo" for item in predictions), 3)
        self.assertEqual(sum(len(item["palpite"]) for item in predictions), 25)
        for rank, expected in ((1, 11), (2, 8), (3, 6)):
            self.assertEqual(sum(f"top{rank}" in item["ranks_selecionados"].split("+") for item in predictions), expected)
        self.assertIn("1", predictions[0]["palpite"])
        self.assertNotIn("1", predictions[1]["palpite"])
        self.assertNotIn("1", predictions[2]["palpite"])
        self.assertIn("pTop1_base", predictions[0])
        self.assertIn("ranking_mudou", predictions[0])
        self.assertAlmostEqual(predictions[0]["P13plus_otimo"], probability)
        self.assertLessEqual(predictions[0]["perda_relativa_soft"], 0.005)
        self.assertEqual(sum(item["tipo_duplo"] != "-" for item in predictions), 5)
        for item in predictions:
            self.assertAlmostEqual(item["CoberturaD12"], item["p(top1)"] + item["p(top2)"])
            self.assertAlmostEqual(item["CoberturaD13"], item["p(top1)"] + item["p(top3)"])
            self.assertAlmostEqual(item["CoberturaD23"], item["p(top2)"] + item["p(top3)"])
            self.assertEqual(item["CoberturaT123"], 1.0)
            if item["tipo"] == "duplo":
                self.assertAlmostEqual(item["double_gain"], item["probabilidade_coberta"] - item["p(top1)"])
                expected_kind = "RecoveryGain" if item["tipo_duplo"] == "D23" else "DoubleGain"
                self.assertEqual(item["gain_kind"], expected_kind)
            elif item["tipo"] == "triplo":
                self.assertEqual(item["tipo_estrutural"], "T123")
                self.assertEqual(item["gain_kind"], "TripleGain")
                self.assertAlmostEqual(item["probabilidade_coberta"], 1.0)
                self.assertAlmostEqual(item["gain_per_extra_mark"], (1 - item["p(top1)"]) / 2)
        distribution = hit_distribution([item["probabilidade_coberta"] for item in predictions])
        self.assertAlmostEqual(probability, sum(distribution[13:]))

        audit = substitution_audit(predictions)
        self.assertTrue(audit)
        self.assertTrue(all(item["DeltaP13plus"] <= 1e-12 for item in audit))
        self.assertEqual({item["JogoOriginal"] for item in audit},
                         {int(item["Jogo"]) for item in predictions if item["tipo"] != "seco"})

    def test_independent_validator_rejects_a_tampered_ticket(self):
        rows = []
        for game in range(1, 15):
            rows.append({
                "Concurso": "1", "Jogo": str(game),
                "Mandante": f"TIME {game} A", "Visitante": f"TIME {game} B",
                "p(1)": "0,50", "p(x)": "0,30", "p(2)": "0,20",
            })
        predictions, _ = optimize(rows, 1.0)
        validate_ticket(predictions)
        predictions[0]["palpite"] = "1X2"
        with self.assertRaisesRegex(ValueError, "Hard Constraints violadas"):
            validate_ticket(predictions)

    def test_optimizer_rejects_invalid_soft_tolerance(self):
        rows = [{
            "Concurso": "1", "Jogo": str(game), "Mandante": f"TIME {game} A",
            "Visitante": f"TIME {game} B", "p(1)": "0,50", "p(x)": "0,30", "p(2)": "0,20",
        } for game in range(1, 15)]
        with self.assertRaisesRegex(ValueError, "intervalo"):
            optimize(rows, 1.0, soft_relative_tolerance=1.0)


if __name__ == "__main__":
    unittest.main()
