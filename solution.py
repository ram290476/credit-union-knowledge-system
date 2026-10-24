"""Submission entry point.

The harness loads this module and calls ``build()``. Only snapshot ingestion
is implemented here; conflict resolution and answer generation follow in
later changes.
"""

from __future__ import annotations

from knowledge.system import KnowledgeSystem


def build() -> KnowledgeSystem:
    return KnowledgeSystem()
