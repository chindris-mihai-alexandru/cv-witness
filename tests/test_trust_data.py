"""Tests for the employer-trust provider layer (scripts/trust_data.py).

Every network call is replaced by an injected transport, so these tests are
deterministic and offline. The transport returns a JSON-RPC envelope exactly as
the live MCP endpoint does, so the parsing under test is the real one.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import trust_data


def envelope(text: str) -> dict:
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": text}]}}


def error_envelope(text: str) -> dict:
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"isError": True, "content": [{"type": "text", "text": text}]}}


NOTE = {
    "id": 7, "kind": "red_flag", "status": "unverified",
    "subject": {"type": "company", "name": "Acme"},
    "text_en": "Pay-to-apply: the posting asks for a fee.",
    "payload": {"type": "pay_to_apply"},
    "evidence": {"type": "page_observed", "observed_at": "2026-11-14"},
    "trust": {"score": 0.77, "confirms": 0, "disputes": 0, "freshness": 1.0},
    "author": "someone", "created_at": "2026-11-15",
}

CORROBORATED = dict(NOTE, kind="red_flag", status="corroborated",
                    trust={"score": 3.1, "confirms": 3, "disputes": 0,
                           "freshness": 0.9})


class EnvelopeTests(unittest.TestCase):
    def test_parses_a_bare_json_envelope(self):
        body = json.dumps(envelope('{"found": false}'))
        parsed = trust_data._parse_envelope(body)
        assert parsed is not None
        self.assertEqual(parsed["result"]["content"][0]["text"], '{"found": false}')

    def test_parses_an_sse_stream(self):
        body = "event: message\r\ndata: " + json.dumps(envelope('{"found": true}')) + "\r\n"
        parsed = trust_data._parse_envelope(body)
        assert parsed is not None
        self.assertEqual(parsed["result"]["content"][0]["text"], '{"found": true}')

    def test_unparseable_body_is_none(self):
        self.assertIsNone(trust_data._parse_envelope("<html>gateway</html>"))


class NoteTests(unittest.TestCase):
    def test_normalise_notes_keeps_the_fields_the_gate_needs(self):
        payload = trust_data._normalise_notes({"found": True, "notes": [NOTE]})
        self.assertTrue(payload["found"])
        note = payload["notes"][0]
        self.assertEqual(note["kind"], "red_flag")
        self.assertEqual(note["score"], 0.77)
        self.assertEqual(note["evidence"], "page_observed")
        self.assertEqual(note["observed_at"], "2026-11-14")
        self.assertEqual(note["subject"], "Acme")

    def test_normalise_notes_tolerates_a_missing_notes_list(self):
        self.assertEqual(trust_data._normalise_notes({"found": False})["notes"], [])

    def test_non_dict_notes_are_skipped(self):
        payload = trust_data._normalise_notes({"found": True, "notes": ["junk", NOTE]})
        self.assertEqual(len(payload["notes"]), 1)

    def test_actionable_requires_the_provider_threshold(self):
        brief = {"notes": [NOTE]}
        self.assertEqual(trust_data.actionable_notes(brief, ("red_flag",)), [])
        self.assertEqual(len(trust_data.all_notes(brief, ("red_flag",))), 1)

    def test_corroborated_status_is_actionable_even_at_low_score(self):
        low = dict(NOTE, status="corroborated", trust={"score": 0.4})
        self.assertEqual(len(trust_data.actionable_notes({"notes": [low]},
                                                          ("red_flag",))), 1)

    def test_score_at_threshold_is_actionable(self):
        at = dict(NOTE, status="unverified",
                  trust={"score": trust_data.CORROBORATED_SCORE})
        self.assertEqual(len(trust_data.actionable_notes({"notes": [at]},
                                                          ("red_flag",))), 1)

    def test_other_kinds_are_ignored(self):
        brief = {"notes": [dict(NOTE, kind="process")]}
        self.assertEqual(trust_data.actionable_notes(brief, ("red_flag",)), [])


class ProviderTests(unittest.TestCase):
    def test_company_not_found_is_reported_not_raised(self):
        transport = lambda payload: envelope('{"found": false, "hint": "No notes yet."}')
        brief = trust_data.hirelog_company("Acme", transport=transport)
        assert brief is not None
        self.assertFalse(brief["found"])
        self.assertEqual(brief["hint"], "No notes yet.")

    def test_company_with_notes(self):
        transport = lambda payload: envelope(json.dumps({"found": True, "notes": [NOTE]}))
        brief = trust_data.hirelog_company("Acme", transport=transport)
        assert brief is not None
        self.assertTrue(brief["found"])
        self.assertEqual(len(brief["notes"]), 1)

    def test_blank_company_name_raises(self):
        with self.assertRaises(trust_data.TrustError):
            trust_data.hirelog_company("   ")

    def test_tool_error_returns_none(self):
        transport = lambda payload: error_envelope("boom")
        self.assertIsNone(trust_data.hirelog_company("Acme", transport=transport))

    def test_unreachable_transport_returns_none(self):
        self.assertIsNone(trust_data.hirelog_company("Acme", transport=lambda p: None))

    def test_non_json_tool_text_is_kept_as_raw(self):
        transport = lambda payload: envelope("plain text, not json")
        brief = trust_data.hirelog_company("Acme", transport=transport)
        assert brief is not None
        self.assertFalse(brief["found"])
        self.assertEqual(brief["raw"], "plain text, not json")

    def test_check_posting_passes_company_and_url(self):
        seen = {}

        def transport(payload):
            seen.update(payload["params"]["arguments"])
            return envelope(json.dumps({"company": "Acme", "notes": [NOTE]}))

        result = trust_data.hirelog_check_posting("https://example.com/job", "Acme",
                                                  transport=transport)
        assert result is not None
        self.assertEqual(seen, {"url": "https://example.com/job", "company": "Acme"})
        self.assertEqual(result["notes"][0]["kind"], "red_flag")

    def test_check_posting_requires_a_url(self):
        with self.assertRaises(trust_data.TrustError):
            trust_data.hirelog_check_posting("  ", transport=lambda p: None)

    def test_market_slug_is_required(self):
        with self.assertRaises(trust_data.TrustError):
            trust_data.hirelog_market("")

    def test_catalog_documents_the_live_provider(self):
        names = {entry["name"] for entry in trust_data.provider_catalog()}
        self.assertIn("hirelog", names)


if __name__ == "__main__":
    unittest.main()
