"""Submission entry point.

The harness loads this module and calls ``build()``. Ingestion, conflict
resolution, and answers are implemented. The practice-question score is recorded
separately.
"""

from __future__ import annotations

from knowledge.system import KnowledgeSystem


def build() -> KnowledgeSystem:
    return KnowledgeSystem()
