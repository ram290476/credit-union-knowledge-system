"""Unit tests for snapshot ingestion, parsing, and the versioned store."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.models import canonical_url  # noqa: E402
from knowledge.parse import parse_markdown  # noqa: E402
from knowledge.snapshot_loader import load_snapshot_dir  # noqa: E402
from solution import build  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "snapshots"


def _page(url: str, markdown: str, title: str = "Page") -> SimpleNamespace:
    return SimpleNamespace(
        url=url,
        title=title,
        markdown=markdown,
        fetched_at="2026-05-12T00:00:00Z",
    )


def _snap(snapshot_id: str, taken_on: str, pages: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(snapshot_id=snapshot_id, taken_on=taken_on, pages=pages)


class ParseTests(unittest.TestCase):
    def test_table_keeps_tiers_and_metrics_apart(self) -> None:
        markdown = """
# Savings

| Account Type | Balance Tier | Dividend Rate | Annual Percentage Yield (APY) |
| --- | --- | --- | --- |
| Share Savings | $10,000 – $24,999.99 | 0.15% | 0.15%1 |
| Share Savings | $25,000+ | 0.20% | 0.20% |
"""
        parsed = parse_markdown(markdown)
        apy = [fact for fact in parsed.facts if fact.metric == "apy"]
        dividend = [fact for fact in parsed.facts if fact.metric == "dividend"]
        self.assertEqual(sorted(fact.number for fact in apy), [0.15, 0.20])
        self.assertEqual(sorted(fact.number for fact in dividend), [0.15, 0.20])
        labels = {fact.label for fact in apy}
        self.assertTrue(any("10,000" in label for label in labels))
        self.assertTrue(any("25,000" in label for label in labels))
        low = next(fact for fact in apy if fact.number == 0.15)
        self.assertIn("tier:", " ".join(low.qualifiers))
        self.assertNotIn("0.20", low.label)

    def test_model_year_and_term_qualifiers(self) -> None:
        markdown = """
| Loan Program | Term | Annual Percentage Rate (As Low As) |
| --- | --- | --- |
| 2024-27 Model Year | 60 Months | 5.39% APR |
| 2021-23 Model Year | 60 Months | 5.64% APR |
"""
        parsed = parse_markdown(markdown)
        facts = [fact for fact in parsed.facts if fact.metric == "apr"]
        self.assertEqual(len(facts), 2)
        newer = next(fact for fact in facts if fact.number == 5.39)
        self.assertIn("term:60m", newer.qualifiers)
        self.assertIn("model:2024-2027", newer.qualifiers)
        self.assertNotEqual(facts[0].label, facts[1].label)

    def test_date_ranges_are_not_model_years(self) -> None:
        parsed = parse_markdown(
            "Rates are effective as of 2026-09-28. 2024-27 Model Year APR is 5.39%.\n"
        )
        models = [q for fact in parsed.facts for q in fact.qualifiers if q.startswith("model:")]
        self.assertIn("model:2024-2027", models)
        self.assertFalse(any(q.startswith("model:2026-") for q in models))

    def test_cell_apr_overrides_yield_header(self) -> None:
        parsed = parse_markdown(
            """
| Account Type | Balance Tier | Annual Percentage Yield |
| --- | --- | --- |
| 2023-26 Model Year | 60 Months | 5.34% APR |
"""
        )
        facts = [fact for fact in parsed.facts if fact.number == 5.34]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].metric, "apr")
        self.assertIn("model:2023-2026", facts[0].qualifiers)
        self.assertIn("term:60m", facts[0].qualifiers)

    def test_prose_apy_and_fee(self) -> None:
        parsed = parse_markdown(
            "# Certificates\n\n6-month certificate APY: 2.95%\n\n"
            "Lost debit card replacement fee: $2.50\n"
        )
        apy = [fact for fact in parsed.facts if fact.metric == "apy"]
        fees = [fact for fact in parsed.facts if fact.metric == "fee"]
        self.assertEqual([fact.number for fact in apy], [2.95])
        self.assertEqual([fact.raw_value for fact in fees], ["$2.50"])
        self.assertIn("term:6m", apy[0].qualifiers)
        self.assertIn("product:certificate", apy[0].qualifiers)

    def test_example_sentence_is_marked(self) -> None:
        parsed = parse_markdown(
            "If you borrow $30,000 at a 5.39% annual percentage rate (APR), "
            "the example payment is illustrative only."
        )
        percents = [fact for fact in parsed.facts if fact.unit == "%"]
        self.assertTrue(percents)
        self.assertIn("example", percents[0].qualifiers)

    def test_long_line_does_not_raise(self) -> None:
        markdown = ("x" * 8000) + "\n\nVisible rate 4.10% APY\n"
        parsed = parse_markdown(markdown)
        self.assertTrue(any(fact.number == 4.10 for fact in parsed.facts))


class StoreTests(unittest.TestCase):
    def test_canonical_url_ignores_www_and_fragment(self) -> None:
        left = canonical_url("https://www.Example.com/rates/certificates/")
        right = canonical_url("https://example.com/rates/certificates#rates")
        self.assertEqual(left, right)

    def test_history_as_of_and_changes(self) -> None:
        snaps = load_snapshot_dir(FIXTURES)
        self.assertEqual(len(snaps), 5)
        system = build()
        for snap in snaps:
            system.ingest(snap)

        latest = system.snapshot_as_of(None)
        assert latest is not None
        self.assertEqual(latest.snapshot_id, "05_2026-09-28_latest")
        may = system.snapshot_as_of("2026-05-31")
        assert may is not None
        self.assertEqual(may.snapshot_id, "02_2026-05-19_recrawl")
        self.assertIsNone(system.snapshot_as_of("2020-01-01"))

        second = system.store.snapshots["02_2026-05-19_recrawl"]
        self.assertIn("https://example-cu.test/promo", second.added_urls)
        self.assertIn("https://example-cu.test/rates/certificates", second.changed_urls)
        self.assertIn("https://example-cu.test/fees", second.unchanged_urls)

        fourth = system.store.snapshots["04_2026-08-27_rebaseline"]
        self.assertIn("https://example-cu.test/promo", fourth.removed_urls)

        history = system.store.history("https://www.example-cu.test/rates/certificates#rates")
        self.assertEqual(len(history), 5)
        self.assertEqual([doc.taken_on for doc in history], [snap.taken_on for snap in snaps])
        self.assertGreater(len({doc.content_hash for doc in history}), 1)

        may_facts = system.store.facts["02_2026-05-19_recrawl"]
        apy_numbers = {fact.number for fact in may_facts if fact.metric == "apy"}
        self.assertIn(3.50, apy_numbers)
        self.assertIn(2.95, apy_numbers)

    def test_out_of_order_ingest_uses_dates(self) -> None:
        snaps = {snap.snapshot_id: snap for snap in load_snapshot_dir(FIXTURES)}
        system = build()
        system.ingest(snaps["05_2026-09-28_latest"])
        system.ingest(snaps["01_2026-05-12_baseline"])
        self.assertEqual(system.snapshot_as_of(None).snapshot_id, "05_2026-09-28_latest")
        self.assertEqual(system.snapshot_as_of("2026-05-15").snapshot_id, "01_2026-05-12_baseline")

    def test_reingest_replaces_snapshot(self) -> None:
        system = build()
        url = "https://example-cu.test/fees"
        system.ingest(
            _snap(
                "01_2026-05-12_baseline",
                "2026-05-12",
                [_page(url, "Lost debit card replacement fee: $2.50")],
            )
        )
        system.ingest(
            _snap(
                "01_2026-05-12_baseline",
                "2026-05-12",
                [_page(url, "Lost debit card replacement fee: $3.00")],
            )
        )
        facts = system.store.facts["01_2026-05-12_baseline"]
        self.assertEqual([fact.number for fact in facts if fact.metric == "fee"], [3.0])
        self.assertEqual(len(system.store.order), 1)

    def test_blank_url_is_skipped(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "01_2026-05-12_baseline",
                "2026-05-12",
                [
                    _page("", "Lost debit card replacement fee: $2.50"),
                    _page("https://example-cu.test/fees", "Lost debit card replacement fee: $2.50"),
                ],
            )
        )
        self.assertEqual(system.store.summary()["page_count"], 1)

    def test_empty_markdown_is_stored(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "01_2026-05-12_baseline",
                "2026-05-12",
                [_page("https://example-cu.test/empty", "")],
            )
        )
        summary = system.store.summary()
        self.assertEqual(summary["page_count"], 1)
        self.assertEqual(summary["fact_count"], 0)
        doc = system.store.pages["01_2026-05-12_baseline"][0]
        self.assertTrue(doc.content_hash)
        self.assertEqual(doc.fetched_at, "2026-05-12T00:00:00Z")


class ContractTests(unittest.TestCase):
    def test_build_exposes_harness_methods(self) -> None:
        system = build()
        self.assertTrue(callable(system.ingest))
        self.assertTrue(callable(system.answer))
        self.assertTrue(callable(system.conflicts))

    def test_answer_abstains_without_digits_until_later_issue(self) -> None:
        system = build()
        for snap in load_snapshot_dir(FIXTURES):
            system.ingest(snap)
        answer = system.answer("What is the 6-month certificate APY?", as_of="2026-05-31")
        self.assertFalse(answer.confident)
        self.assertEqual(answer.sources, [])
        self.assertIsNone(re.search(r"\d", answer.text))
        self.assertIn("don't know", answer.text.lower())
        self.assertIsInstance(system.conflicts(), list)


if __name__ == "__main__":
    unittest.main()
