"""Local copies of the harness boundary types.

The scorer imports ``contract`` before loading ``solution.py``. When that
module is absent (unit tests, smoke script) these dataclasses carry the same
fields, so ``answer`` and ``conflicts`` still satisfy the protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Source:
    url: str
    snapshot_id: str | None = None
    quote: str | None = None


@dataclass
class Answer:
    text: str
    sources: list[Source] = field(default_factory=list)
    confident: bool = True
    conflict_note: str | None = None


@dataclass
class Conflict:
    topic: str
    values: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    resolution: str | None = None
    reason: str | None = None


def boundary_types() -> tuple[type[Answer], type[Conflict], type[Source]]:
    try:
        from contract import Answer as HarnessAnswer
        from contract import Conflict as HarnessConflict
        from contract import Source as HarnessSource
    except ImportError:
        return Answer, Conflict, Source
    return HarnessAnswer, HarnessConflict, HarnessSource
