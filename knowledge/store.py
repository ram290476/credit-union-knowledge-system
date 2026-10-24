"""In-memory history of every page, passage, and fact, keyed by snapshot date."""

from __future__ import annotations

import hashlib

from knowledge.models import Fact, PageDocument, Passage, SnapshotRecord, canonical_url
from knowledge.parse import parse_markdown


class VersionedStore:
    def __init__(self) -> None:
        self.snapshots: dict[str, SnapshotRecord] = {}
        self.order: list[str] = []
        self.pages: dict[str, list[PageDocument]] = {}
        self.passages: dict[str, list[Passage]] = {}
        self.facts: dict[str, list[Fact]] = {}
        self.by_url: dict[str, list[PageDocument]] = {}

    def ingest(self, snapshot: object) -> None:
        snapshot_id = str(getattr(snapshot, "snapshot_id"))
        taken_on = str(getattr(snapshot, "taken_on"))
        if snapshot_id in self.pages:
            self._drop(snapshot_id)

        pages: list[PageDocument] = []
        passages: list[Passage] = []
        facts: list[Fact] = []
        for page in getattr(snapshot, "pages", []) or []:
            url = str(getattr(page, "url", "") or "").strip()
            if not url:
                continue
            markdown = str(getattr(page, "markdown", "") or "")
            title = str(getattr(page, "title", "") or "")
            fetched_at = str(getattr(page, "fetched_at", "") or taken_on)
            canon = canonical_url(url)
            parsed = parse_markdown(markdown)
            document = PageDocument(
                snapshot_id=snapshot_id,
                taken_on=taken_on,
                url=url,
                canonical_url=canon,
                title=title,
                markdown=markdown,
                fetched_at=fetched_at,
                content_hash=_hash(markdown),
                headings=tuple(parsed.headings),
            )
            pages.append(document)
            for item in parsed.passages:
                passages.append(
                    Passage(
                        snapshot_id=snapshot_id,
                        taken_on=taken_on,
                        url=url,
                        canonical_url=canon,
                        title=title,
                        fetched_at=fetched_at,
                        section=item.section,
                        text=item.text,
                        kind=item.kind,
                    )
                )
            for item in parsed.facts:
                facts.append(
                    Fact(
                        snapshot_id=snapshot_id,
                        taken_on=taken_on,
                        url=url,
                        canonical_url=canon,
                        title=title,
                        fetched_at=fetched_at,
                        section=item.section,
                        label=item.label,
                        metric=item.metric,
                        raw_value=item.raw_value,
                        number=item.number,
                        unit=item.unit,
                        qualifiers=item.qualifiers,
                        excerpt=item.excerpt,
                        template=item.template,
                    )
                )

        self.pages[snapshot_id] = pages
        self.passages[snapshot_id] = passages
        self.facts[snapshot_id] = facts
        self.snapshots[snapshot_id] = SnapshotRecord(
            snapshot_id=snapshot_id,
            taken_on=taken_on,
            page_count=len(pages),
            passage_count=len(passages),
            fact_count=len(facts),
        )
        if snapshot_id not in self.order:
            self.order.append(snapshot_id)
        self._reindex_urls()
        self._recompute_changes()

    def ordered_snapshots(self) -> list[SnapshotRecord]:
        return sorted(self.snapshots.values(), key=lambda rec: (rec.taken_on, rec.snapshot_id))

    def snapshot_as_of(self, as_of: str | None) -> SnapshotRecord | None:
        """Latest snapshot whose ``taken_on`` is on or before ``as_of``.

        ``as_of=None`` is the newest snapshot. Dates are ISO ``YYYY-MM-DD``,
        so lexicographic order matches calendar order. Choosing this snapshot
        inside ``answer`` is a later step; the store only records the timeline.
        """

        ordered = self.ordered_snapshots()
        if not ordered:
            return None
        if as_of is None:
            return ordered[-1]
        eligible = [rec for rec in ordered if rec.taken_on <= as_of]
        if not eligible:
            return None
        return eligible[-1]

    def history(self, url: str) -> list[PageDocument]:
        return list(self.by_url.get(canonical_url(url), []))

    def summary(self) -> dict[str, object]:
        rows = []
        for rec in self.ordered_snapshots():
            rows.append(
                {
                    "snapshot_id": rec.snapshot_id,
                    "taken_on": rec.taken_on,
                    "pages": rec.page_count,
                    "passages": rec.passage_count,
                    "facts": rec.fact_count,
                    "added": len(rec.added_urls),
                    "changed": len(rec.changed_urls),
                    "removed": len(rec.removed_urls),
                    "unchanged": len(rec.unchanged_urls),
                }
            )
        return {
            "snapshots": rows,
            "snapshot_count": len(rows),
            "page_count": sum(int(row["pages"]) for row in rows),
            "passage_count": sum(int(row["passages"]) for row in rows),
            "fact_count": sum(int(row["facts"]) for row in rows),
        }

    def _drop(self, snapshot_id: str) -> None:
        self.pages.pop(snapshot_id, None)
        self.passages.pop(snapshot_id, None)
        self.facts.pop(snapshot_id, None)
        self.snapshots.pop(snapshot_id, None)

    def _reindex_urls(self) -> None:
        by_url: dict[str, list[PageDocument]] = {}
        documents: list[PageDocument] = []
        for rec in self.ordered_snapshots():
            documents.extend(self.pages.get(rec.snapshot_id, []))
        for doc in documents:
            by_url.setdefault(doc.canonical_url, []).append(doc)
        self.by_url = by_url

    def _recompute_changes(self) -> None:
        previous: dict[str, str] = {}
        for rec in self.ordered_snapshots():
            current: dict[str, str] = {}
            for doc in self.pages.get(rec.snapshot_id, []):
                current[doc.canonical_url] = doc.content_hash
            current_urls = set(current)
            previous_urls = set(previous)
            added = tuple(sorted(current_urls - previous_urls))
            removed = tuple(sorted(previous_urls - current_urls))
            changed = tuple(
                sorted(url for url in current_urls & previous_urls if current[url] != previous[url])
            )
            unchanged = tuple(
                sorted(url for url in current_urls & previous_urls if current[url] == previous[url])
            )
            self.snapshots[rec.snapshot_id] = SnapshotRecord(
                snapshot_id=rec.snapshot_id,
                taken_on=rec.taken_on,
                page_count=rec.page_count,
                passage_count=rec.passage_count,
                fact_count=rec.fact_count,
                added_urls=added,
                removed_urls=removed,
                changed_urls=changed,
                unchanged_urls=unchanged,
            )
            previous = current


def _hash(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()
