"""Find qualified facts that disagree and choose a winning value.

Two numbers conflict when they are the same kind of fact: same metric, same
term, same balance tier, and the same model-year window (or overlapping
windows for a shifted rate table). APY is not compared with APR. A different
balance tier is not a conflict. Example sentences are ignored.

The winner is the value on the newest snapshot, and on that date the page
with the higher authority score. Rate and fee paths outrank calculators,
promos, blogs, and news.
"""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlsplit

from knowledge.contract_types import boundary_types
from knowledge.models import Fact
from knowledge.store import VersionedStore

# Dividend tracks APY on the same row. Reporting both doubles conflicts
# without a second disagreement.
_COMPARABLE = frozenset({"apy", "apr", "fee", "rate"})
_METRIC_LABEL = {
    "apy": "APY",
    "apr": "APR",
    "dividend": "dividend rate",
    "fee": "fee",
    "rate": "rate",
}
_LOW_PATH = (
    "blog",
    "news",
    "calculator",
    "promo",
    "guidance",
    "learn",
    "article",
    "offer",
    "switch",
)
_HIGH_PATH = ("rate", "fee", "pricing")


def resolve_conflicts(store: VersionedStore) -> list[object]:
    """Return one ``Conflict`` per disagreeing fact group, newest value first."""

    _, conflict_cls, source_cls = boundary_types()
    grouped: dict[tuple, list[Fact]] = defaultdict(list)
    for facts in store.facts.values():
        for fact in facts:
            key = _group_key(fact)
            if key is not None:
                grouped[key].append(fact)

    grouped = _merge_overlapping_models(grouped)
    conflicts = []
    for facts in grouped.values():
        built = _build_conflict(facts, conflict_cls, source_cls)
        if built is not None:
            conflicts.append(built)
    conflicts.sort(key=lambda item: (item.topic, tuple(item.values)))
    return conflicts


def _group_key(fact: Fact) -> tuple | None:
    if fact.metric not in _COMPARABLE or fact.number is None:
        return None
    if "example" in fact.qualifiers:
        return None
    terms = tuple(sorted(q for q in fact.qualifiers if q.startswith("term:")))
    tiers = tuple(sorted(q for q in fact.qualifiers if q.startswith("tier:")))
    models = tuple(sorted(q for q in fact.qualifiers if q.startswith("model:")))
    flags = tuple(q for q in ("jumbo", "special", "roth", "traditional") if q in fact.qualifiers)
    # A sentence that names several terms or windows is not one fact.
    # Long prose often borrows a term from a neighboring offer.
    if len(terms) > 1 or len(models) > 1 or len(fact.label) > 120:
        return None
    # Product words differ by page ("certificate" vs "certificate savings") and
    # would split one rate into several conflicts. Term, tier, and window are enough.
    specific = bool(terms or tiers or models or "jumbo" in flags)
    if specific:
        return ("strict", fact.metric, terms, tiers, models, flags)
    # Without a term or tier, only a change on the same page is a conflict.
    return ("page", fact.canonical_url, fact.template)


def _subject(fact: Fact) -> tuple[str, ...]:
    text = f"{fact.section} {fact.label}".lower()
    text = re.sub(r"\d+(?:\.\d+)?\s*%", " ", text)
    text = re.sub(r"\$\s*\d[\d,]*(?:\.\d+)?", " ", text)
    text = re.sub(r"[^a-z]+", " ", text)
    stop = {
        "the",
        "and",
        "for",
        "with",
        "our",
        "your",
        "this",
        "that",
        "from",
        "per",
        "apy",
        "apr",
        "rate",
        "fee",
        "dividend",
        "annual",
        "percentage",
        "yield",
    }
    tokens = [
        token
        for token in text.split()
        if len(token) > 2 and token not in stop and not token.isdigit()
    ]
    return tuple(sorted(set(tokens)))


def _merge_overlapping_models(grouped: dict[tuple, list[Fact]]) -> dict[tuple, list[Fact]]:
    """Treat a shifted model-year table as the same auto rate, not a new product.

    Windows merge only when the shorter window is mostly covered, so
    2023-2026 can meet 2024-2027 while 2021-2023 stays apart from 2024-2027.
    """

    buckets: dict[tuple, list[tuple]] = defaultdict(list)
    passthrough: dict[tuple, list[Fact]] = {}
    for key, facts in grouped.items():
        if key[0] != "strict":
            passthrough[key] = facts
            continue
        span = _model_span(key[4])
        if span is None:
            passthrough[key] = facts
            continue
        # metric, terms, tiers, flags — model window is compared aside.
        buckets[(key[1], key[2], key[3], key[5])].append((key, span, facts))

    merged: dict[tuple, list[Fact]] = dict(passthrough)
    for bucket_key, items in buckets.items():
        parent = list(range(len(items)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for left in range(len(items)):
            for right in range(left + 1, len(items)):
                if _windows_overlap(items[left][1], items[right][1]):
                    parent[find(right)] = find(left)
        components: dict[int, list[int]] = defaultdict(list)
        for index in range(len(items)):
            components[find(index)].append(index)
        for indexes in components.values():
            facts: list[Fact] = []
            models: list[str] = []
            for index in indexes:
                facts.extend(items[index][2])
                models.extend(items[index][0][4])
            metric, terms, tiers, flags = bucket_key
            key = ("strict", metric, terms, tiers, tuple(sorted(set(models))), flags)
            merged[key] = facts
    return merged


def _model_span(models: tuple[str, ...]) -> tuple[int, int] | None:
    if len(models) != 1:
        return None
    match = re.fullmatch(r"model:(\d+)-(\d+)", models[0])
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _windows_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    start = max(left[0], right[0])
    end = min(left[1], right[1])
    if start > end:
        return False
    overlap = end - start + 1
    shorter = min(left[1] - left[0] + 1, right[1] - right[0] + 1)
    return overlap / shorter >= 0.5


def _build_conflict(facts: list[Fact], conflict_cls: type, source_cls: type) -> object | None:
    by_number: dict[float, list[Fact]] = defaultdict(list)
    for fact in facts:
        if fact.number is None:
            continue
        by_number[round(fact.number, 4)].append(fact)
    if len(by_number) < 2 or len(by_number) > 4:
        return None
    spread = max(by_number) - min(by_number)
    # A 1.99% introductory APR and a 21% purchase APR are different offers.
    if spread > 8:
        return None

    winner = max(
        facts,
        key=lambda fact: (fact.taken_on, _authority(fact.canonical_url), fact.canonical_url),
    )
    winner_numbers = {
        round(fact.number, 4)
        for fact in facts
        if fact.number is not None
        and fact.snapshot_id == winner.snapshot_id
        and fact.canonical_url == winner.canonical_url
    }
    if set(by_number) <= winner_numbers or len(winner_numbers) != 1:
        return None

    ordered = sorted(by_number)
    values = [_format_value(number, by_number[number][0]) for number in ordered]
    winning_values = [
        _format_value(number, by_number[number][0])
        for number in ordered
        if number in winner_numbers
    ]
    others = [value for value in values if value not in winning_values]
    resolution = " and ".join(winning_values)
    topic = _topic(winner, facts)
    reason = (
        f"Resolved to {resolution} from {winner.snapshot_id} ({winner.taken_on}) "
        f"at {winner.url}. That page is the highest-authority source in the newest "
        f"snapshot that states this fact. Other pages or earlier snapshots still "
        f"show {', '.join(others)}."
    )
    sources = []
    for number in ordered:
        best = max(
            by_number[number],
            key=lambda fact: (fact.taken_on, _authority(fact.canonical_url), fact.canonical_url),
        )
        sources.append(
            source_cls(url=best.url, snapshot_id=best.snapshot_id, quote=(best.excerpt or "")[:240])
        )
    return conflict_cls(
        topic=topic,
        values=values,
        sources=sources,
        resolution=resolution,
        reason=reason,
    )


def _authority(url: str) -> int:
    path = urlsplit(url).path.lower()
    score = 0
    if any(part in path for part in _HIGH_PATH):
        score += 5
    if any(part in path for part in _LOW_PATH):
        score -= 5
    segments = [segment for segment in path.split("/") if segment]
    return score - min(len(segments), 6)


def _format_value(number: float, fact: Fact) -> str:
    if fact.unit == "%" or fact.metric in {"apy", "apr", "dividend", "rate"}:
        return f"{number:.2f}%"
    if fact.unit == "$" or fact.metric == "fee":
        return f"${number:.2f}"
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}"


def _topic(winner: Fact, facts: list[Fact]) -> str:
    parts: list[str] = []
    terms = sorted({q for fact in facts for q in fact.qualifiers if q.startswith("term:")})
    for term in terms:
        number = term.split(":", 1)[1]
        if number.endswith("m"):
            parts.append(f"{int(number[:-1])}-month")
        elif number.endswith("y"):
            parts.append(f"{int(number[:-1])}-year")
    models = sorted({q for fact in facts for q in fact.qualifiers if q.startswith("model:")})
    for model in models:
        parts.append(model.split(":", 1)[1] + " model year")
    if any("jumbo" in fact.qualifiers for fact in facts):
        parts.append("jumbo")
    if any("special" in fact.qualifiers for fact in facts):
        parts.append("special")
    if any("roth" in fact.qualifiers for fact in facts):
        parts.append("roth")
    if any("traditional" in fact.qualifiers for fact in facts):
        parts.append("traditional")
    products = sorted(
        {q.split(":", 1)[1] for fact in facts for q in fact.qualifiers if q.startswith("product:")}
    )
    parts.extend(products)
    if not products and winner.metric in {"fee", "rate"}:
        parts.extend(_subject(winner)[:4])
    parts.append(_METRIC_LABEL.get(winner.metric, winner.metric))
    return " ".join(parts)
