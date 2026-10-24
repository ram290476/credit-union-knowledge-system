"""Conflict grouping: same fact, different number, newest authoritative value wins."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.snapshot_loader import load_snapshot_dir  # noqa: E402
from solution import build  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "snapshots"


def _page(url: str, markdown: str, title: str = "Page") -> SimpleNamespace:
    return SimpleNamespace(url=url, title=title, markdown=markdown, fetched_at="2026-01-05")


def _snap(snapshot_id: str, taken_on: str, pages: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(snapshot_id=snapshot_id, taken_on=taken_on, pages=pages)


class AnswerTests(unittest.TestCase):
    def test_as_of_uses_the_snapshot_then_in_effect(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "01_2026-05-12_baseline",
                "2026-05-12",
                [
                    _page(
                        "https://example-cu.test/rates/certificates",
                        "# Certificates\n\n6-month certificate APY: 2.95%\n",
                    )
                ],
            )
        )
        system.ingest(
            _snap(
                "02_2026-05-19_recrawl",
                "2026-05-19",
                [
                    _page(
                        "https://example-cu.test/rates/certificates",
                        "# Certificates\n\n6-month certificate APY: 3.50%\n",
                    )
                ],
            )
        )
        early = system.answer("What is the 6-month certificate APY?", as_of="2026-05-15")
        self.assertIn("2.95%", early.text)
        self.assertNotIn("3.50%", early.text)
        later = system.answer("What is the 6-month certificate APY?", as_of="2026-05-31")
        self.assertIn("3.50%", later.text)
        self.assertNotIn("2.95%", later.text)
        self.assertTrue(later.sources)

    def test_unpublished_rate_abstains_without_digits(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "05_2026-09-28_latest",
                "2026-09-28",
                [_page("https://example-cu.test/blog", "# Loans\n\nWe offer a 7/1 ARM.\n")],
            )
        )
        answer = system.answer("What is your rate on a 7/1 adjustable-rate mortgage?")
        self.assertFalse(answer.confident)
        self.assertIsNone(re.search(r"\d", answer.text))


class ConflictTests(unittest.TestCase):
    def test_selftest_shape_resolves_to_newer_certificate_apy(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "01_2026-01-05_baseline",
                "2026-01-05",
                [
                    _page(
                        "https://example-cu.test/rates/certificates",
                        "# Certificates\n\n6-month certificate APY: 2.95%\n\n"
                        "12-month certificate APY: 3.10%\n",
                    ),
                    _page(
                        "https://example-cu.test/fees",
                        "# Fees\n\nLost debit card replacement fee: $2.50\n",
                    ),
                ],
            )
        )
        system.ingest(
            _snap(
                "02_2026-03-01_update",
                "2026-03-01",
                [
                    _page(
                        "https://example-cu.test/rates/certificates",
                        "# Certificates\n\n6-month certificate APY: 3.50%\n\n"
                        "12-month certificate APY: 3.10%\n",
                    ),
                    _page(
                        "https://example-cu.test/promo",
                        "# Promo\n\nSummer special: 6-month certificate APY 2.95% "
                        "(offer ended 2025-09-30)\n",
                    ),
                ],
            )
        )
        conflicts = system.conflicts()
        six_month = [
            item
            for item in conflicts
            if "6-month" in item.topic and "certificate" in item.topic and "APY" in item.topic
        ]
        self.assertEqual(len(six_month), 1)
        found = six_month[0]
        self.assertIn("2.95%", found.values)
        self.assertIn("3.50%", found.values)
        self.assertEqual(found.resolution, "3.50%")
        self.assertIn("02_2026-03-01_update", found.reason)
        self.assertTrue(any(source.url.endswith("/rates/certificates") for source in found.sources))
        topics = [item.topic for item in conflicts]
        self.assertFalse(any("12-month" in topic and "APY" in topic for topic in topics))
        self.assertFalse(any(item.resolution == "$2.50" for item in conflicts))

    def test_tiers_and_metrics_are_not_conflicts(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "05_2026-09-28_latest",
                "2026-09-28",
                [
                    _page(
                        "https://example-cu.test/rates/savings",
                        """
# Savings

| Account Type | Balance Tier | Dividend Rate | Annual Percentage Yield (APY) |
| --- | --- | --- | --- |
| Share Savings | $10,000 – $24,999.99 | 0.15% | 0.15% |
| Share Savings | $25,000+ | 0.20% | 0.20% |
""",
                    )
                ],
            )
        )
        self.assertEqual(system.conflicts(), [])

    def test_example_sentence_does_not_conflict_with_the_table(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "05_2026-09-28_latest",
                "2026-09-28",
                [
                    _page(
                        "https://example-cu.test/rates/auto",
                        """
# Auto loans

| Loan Program | Term | Annual Percentage Rate (As Low As) |
| --- | --- | --- |
| 2024-27 Model Year | 60 Months | 5.39% APR |

Illustrative only: if you borrow $30,000 at a 9.99% APR with a 60-month term, pay $1.
""",
                    )
                ],
            )
        )
        self.assertEqual(system.conflicts(), [])

    def test_overlapping_model_years_lose_to_the_rate_page(self) -> None:
        table = """
# Rates

| Loan Program | Term | Annual Percentage Rate (As Low As) |
| --- | --- | --- |
| {model} | 60 Months | {rate} APR |
"""
        system = build()
        system.ingest(
            _snap(
                "05_2026-09-28_latest",
                "2026-09-28",
                [
                    _page(
                        "https://example-cu.test/rates/auto",
                        table.format(model="2024-27 Model Year", rate="5.39%"),
                    ),
                    _page(
                        "https://example-cu.test/calculators/vehicle",
                        """
# Calculator

| Account Type | Balance Tier | Annual Percentage Yield |
| --- | --- | --- |
| 2023-26 Model Year | 60 Months | 5.34% APR |
""",
                    ),
                    _page(
                        "https://example-cu.test/rates/auto-older",
                        table.format(model="2021-23 Model Year", rate="5.64%"),
                    ),
                ],
            )
        )
        conflicts = system.conflicts()
        overlapped = [
            item for item in conflicts if "5.39%" in item.values and "5.34%" in item.values
        ]
        self.assertEqual(len(overlapped), 1)
        self.assertEqual(overlapped[0].resolution, "5.39%")
        self.assertIn("60-month", overlapped[0].topic)
        mixed = [item for item in conflicts if "5.64%" in item.values and "5.39%" in item.values]
        self.assertEqual(mixed, [])

    def test_non_overlapping_model_years_stay_separate(self) -> None:
        system = build()
        system.ingest(
            _snap(
                "05_2026-09-28_latest",
                "2026-09-28",
                [
                    _page(
                        "https://example-cu.test/rates/auto",
                        """
| Loan Program | Term | Annual Percentage Rate |
| --- | --- | --- |
| 2024-27 Model Year | 60 Months | 5.39% APR |
| 2021-23 Model Year | 60 Months | 5.64% APR |
""",
                    )
                ],
            )
        )
        self.assertEqual(system.conflicts(), [])

    def test_roth_and_traditional_rows_are_not_the_same_fact(self) -> None:
        table = """
| Certificate | Annual Percentage Yield (APY) |
| --- | --- |
| Roth: 10 Month Fixed Jumbo Special | {roth} |
| Traditional: 10 Month Fixed Jumbo Special | 3.90% |
"""
        system = build()
        system.ingest(
            _snap(
                "01_2026-05-12_baseline",
                "2026-05-12",
                [_page("https://example-cu.test/rates", table.format(roth="3.50%"))],
            )
        )
        system.ingest(
            _snap(
                "05_2026-09-28_latest",
                "2026-09-28",
                [_page("https://example-cu.test/rates", table.format(roth="4.00%"))],
            )
        )
        conflicts = system.conflicts()
        roth = [item for item in conflicts if "roth" in item.topic and "APY" in item.topic]
        self.assertEqual(len(roth), 1)
        self.assertEqual(roth[0].resolution, "4.00%")
        self.assertNotIn("3.90%", roth[0].values)

    def test_fixture_history_resolves_to_latest_certificate(self) -> None:
        system = build()
        for snap in load_snapshot_dir(FIXTURES):
            system.ingest(snap)
        conflicts = system.conflicts()
        six_month = [
            item
            for item in conflicts
            if "6-month" in item.topic
            and "certificate" in item.topic
            and item.topic.endswith("APY")
        ]
        self.assertEqual(len(six_month), 1)
        self.assertEqual(six_month[0].resolution, "3.70%")
        self.assertIn("2.95%", six_month[0].values)
        self.assertTrue(six_month[0].sources)


if __name__ == "__main__":
    unittest.main()
