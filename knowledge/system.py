"""KnowledgeSystem facade. Ingestion, conflicts, and answers are implemented."""

from __future__ import annotations

from knowledge.answer import answer_question
from knowledge.conflicts import resolve_conflicts
from knowledge.models import SnapshotRecord
from knowledge.store import VersionedStore


class KnowledgeSystem:
    """Holds the versioned store built by ``ingest``."""

    def __init__(self) -> None:
        self.store = VersionedStore()
        self._conflicts: list[object] | None = None

    def ingest(self, snapshot: object) -> None:
        """Record one full-site snapshot. The scorer calls this oldest first."""

        self._conflicts = None
        self.store.ingest(snapshot)

    def snapshot_as_of(self, as_of: str | None = None) -> SnapshotRecord | None:
        return self.store.snapshot_as_of(as_of)

    def answer(self, question: str, as_of: str | None = None) -> object:
        """Answer from the snapshot in effect on ``as_of`` (newest if omitted)."""

        return answer_question(self.store, question, as_of, self.conflicts())

    def conflicts(self) -> list[object]:
        """Contradictions across pages and snapshots, each with a winning value."""

        if self._conflicts is None:
            self._conflicts = resolve_conflicts(self.store)
        return list(self._conflicts)
