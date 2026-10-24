"""KnowledgeSystem facade. Ingestion and conflict resolution are implemented."""

from __future__ import annotations

from knowledge.conflicts import resolve_conflicts
from knowledge.contract_types import boundary_types
from knowledge.models import SnapshotRecord
from knowledge.store import VersionedStore


class KnowledgeSystem:
    """Holds the versioned store built by ``ingest``.

    ``conflicts`` reports disagreeing facts and which value won. ``answer``
    still abstains until issue #4.
    """

    def __init__(self) -> None:
        self.store = VersionedStore()

    def ingest(self, snapshot: object) -> None:
        """Record one full-site snapshot. The scorer calls this oldest first."""

        self.store.ingest(snapshot)

    def snapshot_as_of(self, as_of: str | None = None) -> SnapshotRecord | None:
        return self.store.snapshot_as_of(as_of)

    def answer(self, question: str, as_of: str | None = None) -> object:
        del question, as_of
        answer_cls, _, _ = boundary_types()
        return answer_cls(
            text="I don't know; that isn't listed. Please contact us.",
            sources=[],
            confident=False,
            conflict_note=None,
        )

    def conflicts(self) -> list[object]:
        """Contradictions across pages and snapshots, each with a winning value."""

        return resolve_conflicts(self.store)
