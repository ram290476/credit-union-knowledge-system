"""Submission entry point.

The harness loads this module and calls ``build()``. Snapshot ingestion and
conflict resolution are implemented. Answer generation follows in a later change.
"""

from __future__ import annotations

from knowledge.system import KnowledgeSystem


def build() -> KnowledgeSystem:
    return KnowledgeSystem()
