"""Page, passage, and fact records produced during snapshot ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    """Identity for a page across snapshots.

    Lower-case the host, drop a leading ``www.``, drop the fragment, and
    strip a trailing slash. The query string is kept so distinct documents
    stay distinct.
    """

    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    scheme = (parts.scheme or "https").lower()
    return urlunsplit((scheme, host, path, parts.query, ""))


@dataclass(frozen=True)
class PageDocument:
    snapshot_id: str
    taken_on: str
    url: str
    canonical_url: str
    title: str
    markdown: str
    fetched_at: str
    content_hash: str
    headings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Passage:
    snapshot_id: str
    taken_on: str
    url: str
    canonical_url: str
    title: str
    fetched_at: str
    section: str
    text: str
    kind: str


@dataclass(frozen=True)
class Fact:
    """One qualified value taken from a page.

    ``template`` is the section, label, and metric with amounts blanked out,
    so the same statement can be compared across pages and snapshots later.
    """

    snapshot_id: str
    taken_on: str
    url: str
    canonical_url: str
    title: str
    fetched_at: str
    section: str
    label: str
    metric: str
    raw_value: str
    number: float | None
    unit: str
    qualifiers: tuple[str, ...]
    excerpt: str
    template: str


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    taken_on: str
    page_count: int
    passage_count: int
    fact_count: int
    added_urls: tuple[str, ...] = ()
    removed_urls: tuple[str, ...] = ()
    changed_urls: tuple[str, ...] = ()
    unchanged_urls: tuple[str, ...] = ()


@dataclass
class ParsedPassage:
    section: str
    text: str
    kind: str


@dataclass
class ParsedFact:
    section: str
    label: str
    metric: str
    raw_value: str
    number: float | None
    unit: str
    qualifiers: tuple[str, ...]
    excerpt: str
    template: str


@dataclass
class ParseResult:
    headings: list[str] = field(default_factory=list)
    passages: list[ParsedPassage] = field(default_factory=list)
    facts: list[ParsedFact] = field(default_factory=list)
