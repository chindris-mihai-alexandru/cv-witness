import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_cv_numbers as ccn  # noqa: E402


class RespelledClaimTest(unittest.TestCase):
    SOURCE = ("Led a team of 4 engineers. Reduced latency by 15%. "
              "Managed a $300K budget. Grew throughput 3x.")

    def forms(self, text):
        return {form for form, _, _ in ccn.canonical_claims(text)}

    def invented(self, text, source=SOURCE):
        return {form for form, _ in ccn.collect_unverified(text, [source], 2)}

    def test_percent_spellings_share_one_claim(self):
        for text in ("45%", "45 %", "45 percent", "45 per cent", "45 Pct"):
            self.assertIn("45%", self.forms("Reduced latency by " + text + "."), text)
        self.assertEqual(self.invented("Reduced latency by 45 percent."), {"45%"})
        self.assertEqual(self.invented("Reduced latency by 15 percent."), set())

    def test_latex_escaped_percent_is_a_claim(self):
        self.assertIn("95%", self.forms(r"Reduced latency by 95\%."))
        self.assertEqual(self.invented(r"Reduced latency by 95\%."), {"95%"})
        self.assertEqual(self.invented(r"Reduced latency by 15\%."), set())

    def test_currency_codes_and_words_fold_to_symbols(self):
        for text in ("$3M", "$3 M", "$3 million", "USD 3M", "US$3M",
                     "3M USD", "3 million dollars"):
            self.assertIn("$3m", self.forms("Managed a " + text + " budget."), text)
        self.assertIn("€2.5m", self.forms("Closed a €2.5 million deal."))
        self.assertIn("€4m", self.forms("Closed a deal worth EUR 4M."))
        self.assertIn("£900k", self.forms("Won a GBP 900k contract."))
        self.assertEqual(self.invented("Managed a USD 3M budget."), {"$3m"})
        self.assertEqual(self.invented("Managed a 300K USD budget."), set())

    def test_trailing_symbols_and_european_separators(self):
        for text in ("Cut costs by 50 000 € a year.",
                     "Cut costs by 50 000 £ a year.",
                     "Won a € 1,5M deal."):
            self.assertTrue(self.forms(text), text)
        self.assertEqual(self.invented("Cut costs by 40 000 € a year.",
                                       "Cut costs by 50 000 € a year."), {"€40000"})

    def test_pounds_and_lowercase_gbp_are_not_currency(self):
        self.assertNotIn("£20", self.forms("Shipped 20 pounds of parts."))
        self.assertNotIn("£3", self.forms("Wrote 3 gbp converters."))

    def test_spelled_counts_share_a_claim_with_digits(self):
        for text, expected in (("forty engineers", "40 engineers"),
                               ("Forty-Five engineers", "45 engineers"),
                               ("two hundred users", "200 users"),
                               ("forty million users", "40m users")):
            self.assertIn(expected, self.forms("Led " + text + "."), text)
        self.assertEqual(self.invented("Led forty engineers."), {"40 engineers"})
        self.assertEqual(self.invented("Led four engineers."), set())
        self.assertNotIn("1 engineers", self.forms("Was one of the engineers."))
        self.assertIn("100 users", self.forms("One hundred users signed up."))

    def test_fold_multipliers_share_a_claim_with_x(self):
        for text in ("10x", "10 x", "10-fold", "10 fold", "tenfold",
                     "ten-fold", "Tenfold"):
            self.assertIn("10x", self.forms("Improved throughput " + text + "."), text)
        self.assertEqual(self.invented("Improved throughput tenfold."), {"10x"})
        self.assertEqual(self.invented("Improved throughput threefold."), set())
        self.assertEqual(self.forms("A twofold approach and a threefold mission."), set())

    def test_years_and_single_digits_remain_non_claims(self):
        self.assertFalse(ccn.is_claim("2026"))
        self.assertFalse(ccn.is_claim("4"))
        self.assertTrue(ccn.is_claim("45"))


if __name__ == "__main__":
    unittest.main()
