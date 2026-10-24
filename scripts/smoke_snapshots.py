#!/usr/bin/env python3
"""Ingest five on-disk snapshots and print a summary.

Default input is the synthetic fixture set committed for CI. Pass
``--snapshots`` to point at an unpacked participant kit. The kit itself is
not part of this repository.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.snapshot_loader import load_snapshot_dir  # noqa: E402
from solution import build  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "snapshots"


def run(root: Path, min_facts: int) -> dict[str, object]:
    snapshots = load_snapshot_dir(root)
    if len(snapshots) != 5:
        raise SystemExit(f"expected 5 snapshots in {root}, found {len(snapshots)}")
    system = build()
    started = time.perf_counter()
    for snap in snapshots:
        system.ingest(snap)
        record = system.store.snapshots[snap.snapshot_id]
        print(
            f"ingest {snap.snapshot_id} taken_on={snap.taken_on} "
            f"pages={record.page_count} passages={record.passage_count} "
            f"facts={record.fact_count} added={len(record.added_urls)} "
            f"changed={len(record.changed_urls)} removed={len(record.removed_urls)}",
            flush=True,
        )
    elapsed = time.perf_counter() - started
    summary = system.store.summary()
    summary["elapsed_s"] = round(elapsed, 3)
    current = system.snapshot_as_of(None)
    may = system.snapshot_as_of("2026-05-31")
    summary["latest"] = None if current is None else current.snapshot_id
    summary["as_of_2026_05_31"] = None if may is None else may.snapshot_id
    if int(summary["fact_count"]) < min_facts:
        raise SystemExit(f"fact_count {summary['fact_count']} is below {min_facts}")
    ids = {snap.snapshot_id for snap in snapshots}
    if "02_2026-05-19_recrawl" in ids and summary["as_of_2026_05_31"] != "02_2026-05-19_recrawl":
        raise SystemExit(f"as_of 2026-05-31 resolved to {summary['as_of_2026_05_31']}")
    if "05_2026-09-28_latest" in ids and summary["latest"] != "05_2026-09-28_latest":
        raise SystemExit(f"latest resolved to {summary['latest']}")
    for snap in snapshots:
        ingested = system.store.snapshots[snap.snapshot_id].page_count
        if ingested != len(snap.pages):
            raise SystemExit(f"{snap.snapshot_id} dropped pages: {ingested} != {len(snap.pages)}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test snapshot ingestion")
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=FIXTURES,
        help="directory of snapshot folders (default: synthetic five-snapshot fixtures)",
    )
    parser.add_argument("--min-facts", type=int, default=1)
    args = parser.parse_args()
    summary = run(args.snapshots, args.min_facts)
    print(json.dumps(summary, indent=2))
    print("smoke ok")


if __name__ == "__main__":
    main()
