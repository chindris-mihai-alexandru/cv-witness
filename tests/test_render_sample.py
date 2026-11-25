"""Unit tests for the canonical house-style template filler (render_sample).

fill_template is the single DRY path used by both the public synthetic sample
and any tailored CV, so its escaping and placeholder contract are covered here.
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import render_sample as rs


TEMPLATE = "<h1>{{NAME}}</h1><div>{{SKILLS_BLOCK}}</div><p>{{ROLE}}</p>"


class FillTemplateTests(unittest.TestCase):
    def test_scalar_fields_are_html_escaped(self):
        fields = {"NAME": 'A & B <c> "d"', "SKILLS_BLOCK": "<p>raw</p>", "ROLE": "Engineer"}
        out = rs.fill_template(TEMPLATE, fields)
        self.assertIn("A &amp; B &lt;c&gt; &quot;d&quot;", out)
        self.assertIn("<p>raw</p>", out)  # block fields pass through as trusted HTML

    def test_block_fields_are_not_escaped(self):
        fields = {"NAME": "Alex", "SKILLS_BLOCK": '<ul><li>x &amp; y</li></ul>', "ROLE": "R"}
        out = rs.fill_template(TEMPLATE, fields)
        self.assertIn('<ul><li>x &amp; y</li></ul>', out)

    def test_missing_field_raises(self):
        with self.assertRaises(ValueError):
            rs.fill_template(TEMPLATE, {"NAME": "Alex", "ROLE": "R"})

    def test_extra_field_raises(self):
        with self.assertRaises(ValueError):
            rs.fill_template(TEMPLATE, {"NAME": "A", "SKILLS_BLOCK": "", "ROLE": "R", "EXTRA": "x"})

    def test_no_placeholders_remain(self):
        fields = {"NAME": "Alex", "SKILLS_BLOCK": "", "ROLE": "R"}
        out = rs.fill_template(TEMPLATE, fields)
        self.assertNotIn("{{", out)

    def test_summary_paragraph_is_justified_in_canonical_template(self):
        root = Path(rs.__file__).resolve().parents[1]
        template = (root / "template.html").read_text(encoding="utf-8")
        self.assertIn('<p class="just">{{SUMMARY}}</p>', template)

    def test_margin_override_replaces_all_three_tokens(self):
        src = ":root { --m-top: 18mm; --m-side: 13mm; --m-bottom: 14mm; --font: 9.3pt; }"
        out = rs._apply_margin(src, 15)
        self.assertIn("--m-top: 15mm", out)
        self.assertIn("--m-side: 15mm", out)
        self.assertIn("--m-bottom: 15mm", out)
        self.assertIn("--font: 9.3pt", out)  # non-margin tokens untouched
        self.assertNotIn("18mm", out)

    def test_sample_fields_match_canonical_template(self):
        import json
        from pathlib import Path
        root = Path(rs.__file__).resolve().parents[1]
        template = (root / "template.html").read_text(encoding="utf-8")
        fields = json.loads((root / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
        out = rs.fill_template(template, fields)  # must not raise
        self.assertNotIn("{{", out)


if __name__ == "__main__":
    unittest.main()
