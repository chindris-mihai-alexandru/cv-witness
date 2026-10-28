"""Synthetic tests for the grounded fit scorer. No PDF tools or personal data are needed."""
import contextlib
import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import cv_checks
from scripts import fit_score as fit

TODAY = datetime.date(2026, 10, 28)
EVIDENCE = (
    "Handled customer incidents in Jira and coordinated escalations across engineering teams.\n"
    "Wrote résumé reviews for four teams daily.\n"
    "Automated regression suites with Postman and PowerShell.\n"
)
QUOTE = "handled customer incidents in Jira"


def criterion(cid, weight=10, levels=4, **extra):
    return {"id": cid, "weight": weight, "question": "How much direct experience is shown?",
            "levels": [f"Level {i} described as a situation" for i in range(levels)], **extra}


def criteria(*items):
    return {"schema_version": 1, "criteria": list(items)}


def judgments(**items):
    return {"schema_version": 1, "judgments": items}


def judged(level, confidence=1.0, evidence=(QUOTE,)):
    return {"level": level, "confidence": confidence, "evidence": list(evidence)}


class FitScoreTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.evidence = self.root / "evidence.md"
        self.evidence.write_text(EVIDENCE, encoding="utf-8")

    def run_score(self, criteria_doc, judgments_doc, **options):
        options.setdefault("today", TODAY)
        return fit.score(criteria_doc, judgments_doc, [self.evidence], **options)

    def write(self, name, value, raw=False):
        path = self.root / name
        path.write_text(value if raw else json.dumps(value), encoding="utf-8")
        return path

    def run_cli(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = fit.main(list(arguments))
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()


class ScoringTests(FitScoreTestCase):
    def test_verified_top_level_is_great_without_review(self):
        result = self.run_score(criteria(criterion("incidents")), judgments(incidents=judged(3)))
        self.assertEqual((result["verdict"], result["score"], result["needs_review"]), ("great", 100.0, False))
        self.assertEqual(result["strengths"], ["incidents"])

    def test_claim_without_verified_quote_is_capped_and_flagged(self):
        result = self.run_score(criteria(criterion("incidents")), judgments(incidents=judged(3, evidence=())))
        self.assertEqual((result["verdict"], result["score"]), ("bad", 40.0))
        self.assertIn("ungrounded_claim", result["review_reasons"])
        self.assertFalse(result["breakdown"][0]["grounded"])

    def test_fabricated_quote_does_not_ground_and_is_flagged(self):
        made_up = "Led a global fifty person incident team"
        result = self.run_score(criteria(criterion("incidents")), judgments(incidents=judged(3, evidence=(made_up,))))
        self.assertEqual(result["score"], 40.0)
        self.assertEqual(result["breakdown"][0]["unverified_quotes"], 1)
        self.assertEqual(set(result["review_reasons"]), {"ungrounded_claim", "unverified_quote"})

    def test_quote_matching_ignores_case_punctuation_and_accents(self):
        for quote in ("HANDLED customer incidents, in Jira!", "Wrote resume reviews for four teams"):
            result = self.run_score(criteria(criterion("a")), judgments(a=judged(3, evidence=(quote,))))
            self.assertEqual(result["breakdown"][0]["verified_quotes"], 1, quote)

    def test_short_or_partial_word_quotes_do_not_ground(self):
        for quote in ("Jira incident handling", "customer incidents in Ji"):
            result = self.run_score(criteria(criterion("a")), judgments(a=judged(3, evidence=(quote,))))
            self.assertEqual(result["breakdown"][0]["verified_quotes"], 0, quote)

    def test_low_claims_need_no_evidence(self):
        result = self.run_score(criteria(criterion("a")), judgments(a=judged(1, evidence=())))
        self.assertEqual(result["score"], 33.3)
        self.assertTrue(result["breakdown"][0]["grounded"])
        self.assertFalse(result["needs_review"])

    def test_second_evidence_file_is_searched(self):
        second = self.root / "second.md"
        second.write_text("Mentored a colleague through environments and ticket process.", encoding="utf-8")
        result = fit.score(criteria(criterion("a")),
                           judgments(a=judged(3, evidence=("mentored a colleague through environments",))),
                           [self.evidence, second], today=TODAY)
        self.assertEqual(result["breakdown"][0]["verified_quotes"], 1)

    def test_probabilities_give_expected_score_and_derived_confidence(self):
        result = self.run_score(criteria(criterion("a", levels=3)),
                                judgments(a={"probabilities": [0.1, 0.2, 0.7], "evidence": [QUOTE]}))
        self.assertEqual(result["score"], 80.0)
        self.assertAlmostEqual(result["breakdown"][0]["confidence"], 0.27, places=2)

    def test_probabilities_summing_to_rounding_error_are_accepted(self):
        result = self.run_score(criteria(criterion("a", levels=3)),
                                judgments(a={"probabilities": [0.33, 0.33, 0.33], "evidence": [QUOTE]}))
        self.assertEqual(result["score"], 50.0)

    def test_uncertain_judgment_widens_range_and_requests_review(self):
        result = self.run_score(criteria(criterion("a")), judgments(a=judged(2, 0.5)))
        self.assertEqual((result["verdict"], result["score"]), ("fair", 55.6))
        self.assertEqual(result["range"], [24.1, 87.0])
        self.assertEqual(result["review_reasons"], ["range_crosses_band"])
        self.assertTrue(result["needs_review"])

    def test_weights_decide_the_mix_and_gaps_sort_by_weight(self):
        result = self.run_score(criteria(criterion("big", 30), criterion("small", 10), criterion("mid", 20)),
                                judgments(big=judged(0), small=judged(0), mid=judged(3)))
        self.assertEqual(result["score"], 33.3)
        self.assertEqual(result["gaps"], ["big", "small"])
        self.assertEqual(result["strengths"], ["mid"])

    def test_custom_bands_change_the_verdict(self):
        base = (criteria(criterion("a")), judgments(a=judged(2, 1.0)))
        self.assertEqual(self.run_score(*base)["verdict"], "good")
        self.assertEqual(self.run_score(*base, bands=(90.0, 80.0, 70.0))["verdict"], "bad")


class CoverageAndGateTests(FitScoreTestCase):
    def test_low_coverage_gives_no_band(self):
        result = self.run_score(criteria(criterion("a"), criterion("b")), judgments(a=judged(3)))
        self.assertEqual((result["verdict"], result["score"], result["partial_score"]), ("insufficient_evidence", None, 100.0))
        self.assertEqual(result["not_assessed"], ["b"])
        self.assertTrue(result["needs_review"])

    def test_coverage_threshold_is_configurable(self):
        result = self.run_score(criteria(criterion("a"), criterion("b")), judgments(a=judged(3)), min_coverage=0.5)
        self.assertEqual(result["verdict"], "great")

    def test_failed_gate_blocks_regardless_of_score(self):
        result = self.run_score(criteria(criterion("skill", 90), criterion("auth", 10, gate_min=0.5)),
                                judgments(skill=judged(3), auth=judged(0)))
        self.assertEqual((result["verdict"], result["blocked_by"]), ("blocked", ["auth"]))

    def test_failed_gate_outranks_low_coverage(self):
        result = self.run_score(criteria(criterion("a", 10, gate_min=0.5), criterion("b", 90)), judgments(a=judged(0)))
        self.assertEqual(result["verdict"], "blocked")

    def test_unassessed_gate_cannot_be_cleared(self):
        result = self.run_score(criteria(criterion("skill", 90), criterion("auth", 10, gate_min=0.5)),
                                judgments(skill=judged(3)), min_coverage=0.5)
        self.assertEqual(result["verdict"], "insufficient_evidence")

    def test_zero_weight_gate_passes_without_changing_the_score(self):
        result = self.run_score(criteria(criterion("auth", 0, gate_min=0.5), criterion("skill", 10)),
                                judgments(auth=judged(3), skill=judged(3)))
        self.assertEqual((result["verdict"], result["score"]), ("great", 100.0))
        self.assertEqual(result["breakdown"][0]["weight_share"], 0.0)


class ExperienceTests(FitScoreTestCase):
    def years(self, ranges, min_years=5, **options):
        return self.run_score(criteria({"id": "seniority", "weight": 10, "min_years": min_years}), judgments(),
                              experience=ranges, **options)["breakdown"][0]["score"]

    def test_overlapping_roles_count_once(self):
        # 24 + 19 months written, 36 months of calendar coverage.
        self.assertEqual(self.years(["2020-01:2021-12", "2021-06:2022-12"]), 60.0)

    def test_adjacent_months_merge_and_gaps_do_not(self):
        self.assertEqual(self.years(["2020-01:2020-06", "2020-07:2020-12"], min_years=1), 100.0)
        self.assertEqual(self.years(["2020-01:2020-06", "2020-08:2020-12"], min_years=1), 91.7)

    def test_present_uses_the_supplied_date_and_future_months_are_clipped(self):
        self.assertEqual(self.years(["2026-01:present"], min_years=1), 83.3)
        self.assertEqual(self.years(["2026-09:2030-01"], min_years=1), 16.7)

    def test_range_starting_in_the_future_counts_nothing(self):
        self.assertEqual(self.years(["2030-01:2031-01"], min_years=1), 0.0)

    def test_malformed_ranges_are_rejected(self):
        for bad in ("2020-13:2021-01", "2021-05:2020-01", "2020-01", "2020-01:soon", "20-01:2021-01"):
            with self.assertRaises(cv_checks.CheckError, msg=bad):
                self.years([bad])

    def test_missing_experience_leaves_the_criterion_unassessed(self):
        result = self.run_score(criteria({"id": "seniority", "weight": 10, "min_years": 5}), judgments())
        self.assertEqual(result["not_assessed"], ["seniority"])

    def test_computed_criterion_cannot_be_judged(self):
        with self.assertRaises(cv_checks.CheckError):
            self.run_score(criteria({"id": "seniority", "weight": 10, "min_years": 5}),
                           judgments(seniority=judged(1)), experience=["2020-01:2021-01"])

    def test_too_many_ranges_are_rejected(self):
        with self.assertRaises(cv_checks.CheckError):
            self.years(["2020-01:2020-02"] * 51)


class ValidationTests(FitScoreTestCase):
    def rejects(self, criteria_doc, judgments_doc=None):
        with self.assertRaises(cv_checks.CheckError):
            self.run_score(criteria_doc, judgments_doc or judgments())

    def test_invalid_criteria_are_rejected(self):
        good = criterion("a")
        cases = [
            criteria(good, criterion("a")),
            criteria(criterion("Bad-Id")),
            criteria(criterion("a", weight=-1)),
            criteria(criterion("a", weight=True)),
            criteria(criterion("a", weight="10")),
            criteria(criterion("a", weight=float("nan"))),
            criteria(criterion("a", weight=0)),
            criteria(criterion("a", 0, gate_min=0.5)),
            criteria(criterion("a", gate_min=0)),
            criteria(criterion("a", levels=1)),
            criteria(criterion("a", levels=11)),
            criteria({**criterion("a"), "levels": ["only", ""]}),
            criteria({**criterion("a"), "min_years": 3}),
            criteria({"id": "a", "weight": 10}),
            criteria({"id": "a", "weight": 10, "min_years": 0}),
            criteria({**good, "surprise": 1}),
            criteria(*[criterion(f"c{i}") for i in range(31)]),
            criteria(),
            {"criteria": [good]},
            {**criteria(good), "schema_version": 2},
            {**criteria(good), "extra": 1},
            [good],
        ]
        for case in cases:
            with self.subTest(case=str(case)[:60]):
                self.rejects(case)

    def test_invalid_judgments_are_rejected(self):
        base = criteria(criterion("a"))
        cases = [
            judgments(ghost=judged(1)),
            judgments(a=judged(4)),
            judgments(a=judged(-1)),
            judgments(a=judged(True)),
            judgments(a=judged(1.0)),
            judgments(a={"level": 1}),
            judgments(a={"level": 1, "confidence": "certain"}),
            judgments(a={"level": 1, "confidence": 1.5}),
            judgments(a={"level": 1, "confidence": True}),
            judgments(a={"level": 1, "probabilities": [0.25] * 4, "confidence": 1}),
            judgments(a={"probabilities": [0.25] * 3}),
            judgments(a={"probabilities": [0.5, 0.5, 0.5, 0.5]}),
            judgments(a={"probabilities": [-0.2, 0.4, 0.4, 0.4]}),
            judgments(a={"probabilities": [0.25] * 4, "confidence": 0.9}),
            judgments(a={"confidence": 1}),
            judgments(a={"level": 1, "confidence": 1, "evidence": "not a list"}),
            judgments(a=judged(1, evidence=[7])),
            judgments(a=judged(1, evidence=["four word quote here"] * 11)),
            judgments(a="level 2"),
            {"schema_version": 1, "judgments": []},
            {"judgments": {}},
            {**judgments(), "extra": 1},
        ]
        for case in cases:
            with self.subTest(case=str(case)[:60]):
                self.rejects(base, case)

    def test_evidence_is_required_and_must_be_text(self):
        with self.assertRaises(cv_checks.CheckError):
            fit.score(criteria(criterion("a")), judgments(), [], today=TODAY)
        pdf = self.root / "evidence.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        with self.assertRaises(cv_checks.CheckError):
            fit.score(criteria(criterion("a")), judgments(), [pdf], today=TODAY)

    def test_bad_bands_are_rejected(self):
        for bad in ("80,65", "80,80,50", "50,65,80", "x,y,z", "101,65,50", "80,65,0"):
            with self.assertRaises(cv_checks.CheckError, msg=bad):
                fit.parse_bands(bad)


class CommandLineTests(FitScoreTestCase):
    def files(self, criteria_doc=None, judgments_doc=None):
        return (self.write("criteria.json", criteria_doc or criteria(criterion("a"))),
                self.write("judgments.json", judgments_doc or judgments(a=judged(3))))

    def test_success_prints_json_and_exits_zero(self):
        criteria_file, judgments_file = self.files()
        code, out, err = self.run_cli(str(criteria_file), str(judgments_file), "--evidence", str(self.evidence))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["verdict"], "great")

    def test_bad_inputs_exit_two_without_a_traceback(self):
        criteria_file, judgments_file = self.files()
        duplicate = self.write("duplicate.json", '{"schema_version": 1, "schema_version": 1, "criteria": []}', raw=True)
        nan = self.write("nan.json", '{"schema_version": 1, "judgments": {}, "judge": NaN}', raw=True)
        huge = self.write("huge.json", " " * (fit.MAX_JSON_BYTES + 1), raw=True)
        text = self.write("notes.txt", "{}", raw=True)
        cases = [
            (str(duplicate), str(judgments_file)), (str(criteria_file), str(nan)),
            (str(huge), str(judgments_file)), (str(text), str(judgments_file)),
            (str(self.root / "missing.json"), str(judgments_file)),
        ]
        for first, second in cases:
            code, out, err = self.run_cli(first, second, "--evidence", str(self.evidence))
            self.assertEqual((code, out), (2, ""), first)
            self.assertTrue(err.startswith("fit-score: "))
            self.assertNotIn("Traceback", err)

    def test_published_worked_example_stays_accurate(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "fit"
        code, out, err = self.run_cli(
            str(example / "criteria.json"), str(example / "judgments.json"),
            "--evidence", str(example / "evidence.md"),
            "--experience", "2019-03:2023-06", "--experience", "2022-01:2023-09", "--today", "2026-10-28")
        result = json.loads(out)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((result["verdict"], result["score"]), ("great", 80.6))
        self.assertEqual(result["review_reasons"], ["range_crosses_band"])
        self.assertEqual({row["id"]: row["score"] for row in result["breakdown"]}["seniority"], 91.7)

    def test_option_validation(self):
        criteria_file, judgments_file = self.files()
        base = [str(criteria_file), str(judgments_file), "--evidence", str(self.evidence)]
        for extra in (["--today", "tomorrow"], ["--min-coverage", "0"], ["--min-coverage", "1.5"],
                      ["--bands", "1,2,3"], ["--experience", "oops"]):
            code, _, _ = self.run_cli(*base, *extra)
            self.assertEqual(code, 2, extra)
        self.assertEqual(self.run_cli(str(criteria_file), str(judgments_file))[0], 2)

    def test_output_and_errors_never_echo_private_wording(self):
        secret = "SENTINELPASSAGE"
        criteria_file, judgments_file = self.files(
            criteria(criterion("a"), {**criterion("b"), "question": f"{secret} question text"}),
            judgments(a=judged(3, evidence=(f"{secret} fabricated quote with enough words",)),
                      b=judged(9)))
        code, out, err = self.run_cli(str(criteria_file), str(judgments_file), "--evidence", str(self.evidence))
        self.assertEqual(code, 2)
        self.assertNotIn(secret, out + err)
        self.assertNotIn(str(self.root), err)
        judgments_file = self.write("judgments.json", judgments(a=judged(3, evidence=(f"{secret} fabricated quote with enough words",))))
        code, out, err = self.run_cli(str(criteria_file), str(judgments_file), "--evidence", str(self.evidence),
                                      "--min-coverage", "0.4")
        self.assertEqual(code, 0)
        self.assertNotIn(secret, out + err)
        self.assertNotIn(str(self.root), out)


if __name__ == "__main__":
    unittest.main()