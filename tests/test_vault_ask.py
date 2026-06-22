"""Tests for vault-ask. Run: python3 -m unittest discover -s tests

Requires ripgrep (`rg`) on PATH for the candidate-selection tests.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vault_ask  # noqa: E402


class TestQueryTerms(unittest.TestCase):
    def test_strips_stopwords_and_short_tokens(self):
        terms = vault_ask.query_terms("What did I decide about the pricing for Acme?")
        self.assertIn("decide", terms)
        self.assertIn("pricing", terms)
        self.assertIn("acme", terms)
        self.assertNotIn("what", terms)
        self.assertNotIn("the", terms)
        self.assertNotIn("for", terms)

    def test_french_stopwords(self):
        terms = vault_ask.query_terms("quel est le financement retenu pour le projet")
        self.assertIn("financement", terms)
        self.assertIn("projet", terms)
        self.assertNotIn("quel", terms)
        self.assertNotIn("retenu", terms)


class TestRefusalDetection(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(vault_ask.is_refusal(vault_ask.REFUSAL))

    def test_punctuation_and_case_insensitive(self):
        # A reformulated refusal must still count as a refusal (safety guardrail).
        self.assertTrue(vault_ask.is_refusal("no note in the vault answers this question"))
        self.assertTrue(vault_ask.is_refusal("No note in the vault answers this question."))

    def test_real_answer_is_not_a_refusal(self):
        self.assertFalse(vault_ask.is_refusal("The price is 49 EUR [[Pricing]]."))


class TestPromptGuardrails(unittest.TestCase):
    def test_prompt_carries_sources_and_rules(self):
        notes = [{"link": "[[Decisions/Pricing|Pricing]]", "excerpt": "Price set to 49 EUR."}]
        prompt = vault_ask.build_prompt("what is the price", notes)
        self.assertIn("[[Decisions/Pricing|Pricing]]", prompt)
        self.assertIn(vault_ask.REFUSAL, prompt)
        self.assertIn("Use ONLY the note excerpts", prompt)
        self.assertIn("Price set to 49 EUR", prompt)


class TestCandidateSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        for p in sorted(self.tmp.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        self.tmp.rmdir()

    def test_rare_term_outranks_ubiquitous_term(self):
        # "project" is ubiquitous (low IDF); "zylophone" is rare (high IDF).
        for i in range(8):
            (self.tmp / f"noise{i}.md").write_text(
                "# Project\n" + ("project project project\n" * 20), encoding="utf-8")
        (self.tmp / "target.md").write_text(
            "# Decision\nThe chosen budget tool is Zylophone, for the project.\n",
            encoding="utf-8")
        notes = vault_ask.candidate_notes(self.tmp, "budget zylophone project", limit=5)
        self.assertTrue(notes)
        self.assertEqual(Path(notes[0]["file"]).stem, "target")

    def test_no_terms_returns_empty(self):
        self.assertEqual(vault_ask.candidate_notes(self.tmp, "what is the", limit=5), [])

    def test_excerpt_keeps_answer_on_adjacent_line(self):
        # The keyword and the actual answer often sit on neighbouring (wrapped)
        # lines; the context window must keep both.
        note = self.tmp / "n.md"
        note.write_text(
            "# Heading\nThe chosen value is 49 EUR\nfor the pricing plan.\n",
            encoding="utf-8")
        excerpt = vault_ask.note_excerpt(note, ["pricing"])
        self.assertIn("49 EUR", excerpt)        # answer line (no keyword) kept via context
        self.assertIn("pricing", excerpt)


class TestAsk(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        for p in sorted(self.tmp.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        self.tmp.rmdir()

    def test_synthesizes_with_citation(self):
        (self.tmp / "decision.md").write_text(
            "# Decision\nThe chosen budget tool is Zylophone.\n", encoding="utf-8")
        answer = "The chosen tool is Zylophone [[decision|decision]]."
        with patch.object(vault_ask, "run_llm", return_value=answer):
            res = vault_ask.ask(self.tmp, "which budget tool zylophone")
        self.assertTrue(res["grounded"])
        self.assertEqual(res["answer"], answer)
        self.assertTrue(res["sources"])

    def test_refuses_when_no_candidates(self):
        with patch.object(vault_ask, "run_llm") as llm:
            res = vault_ask.ask(self.tmp, "completely unrelated xyzzy quux")
        llm.assert_not_called()
        self.assertFalse(res["grounded"])
        self.assertEqual(res["answer"], vault_ask.REFUSAL)

    def test_refusal_from_llm_drops_sources(self):
        (self.tmp / "note.md").write_text("# Note\nZylophone budget tool.\n", encoding="utf-8")
        with patch.object(vault_ask, "run_llm", return_value="No note in the vault answers this question"):
            res = vault_ask.ask(self.tmp, "zylophone budget")
        self.assertFalse(res["grounded"])
        self.assertEqual(res["answer"], vault_ask.REFUSAL)
        self.assertEqual(res["sources"], [])

    def test_no_llm_returns_candidates_not_hallucination(self):
        (self.tmp / "note.md").write_text("# Note\nZylophone budget tool.\n", encoding="utf-8")
        with patch.object(vault_ask, "run_llm", return_value=None):
            res = vault_ask.ask(self.tmp, "zylophone budget")
        self.assertFalse(res["grounded"])
        self.assertIsNone(res["answer"])
        self.assertEqual(res["reason"], "no-llm")
        self.assertTrue(res["candidates"])

    def test_sources_only_skips_llm(self):
        (self.tmp / "note.md").write_text("# Note\nZylophone budget tool.\n", encoding="utf-8")
        with patch.object(vault_ask, "run_llm") as llm:
            res = vault_ask.ask(self.tmp, "zylophone budget", sources_only=True)
        llm.assert_not_called()
        self.assertEqual(res["mode"], "sources-only")
        self.assertTrue(res["sources"])
        self.assertIsNone(res["answer"])

    def test_missing_ripgrep_gives_clear_reason(self):
        with patch.object(vault_ask.shutil, "which", return_value=None):
            res = vault_ask.ask(self.tmp, "anything at all")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "ripgrep-not-found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
