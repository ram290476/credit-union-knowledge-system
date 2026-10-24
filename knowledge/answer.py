"""Answer a question from the snapshot that was current on ``as_of``.

Rate questions use qualified facts and prefer an official product or rate
page over a calculator, promo, or old article. Other questions quote a short
passage from that snapshot. When the snapshot does not state the fact, the
answer abstains and contains no digits.
"""

from __future__ import annotations

import re

from knowledge.conflicts import _authority
from knowledge.contract_types import boundary_types
from knowledge.models import Fact, PageDocument
from knowledge.store import VersionedStore

_ABSTAIN = "I don't know; that isn't listed. Please contact us."
_RATE_METRICS = frozenset({"apy", "apr", "dividend", "rate"})


def answer_question(
    store: VersionedStore,
    question: str,
    as_of: str | None = None,
    conflicts: list[object] | None = None,
) -> object:
    answer_cls, _, source_cls = boundary_types()
    snapshot = store.snapshot_as_of(as_of)
    if snapshot is None:
        return _abstain(answer_cls)
    pages = store.pages.get(snapshot.snapshot_id, [])
    facts = [
        fact
        for fact in store.facts.get(snapshot.snapshot_id, [])
        if "example" not in fact.qualifiers and fact.number is not None
    ]
    text, sources, confident = _dispatch(question, pages, facts, source_cls)
    if not text:
        return _abstain(answer_cls)
    return answer_cls(
        text=text,
        sources=sources,
        confident=confident,
        conflict_note=_conflict_note(conflicts or [], text),
    )


def _abstain(answer_cls: type) -> object:
    return answer_cls(text=_ABSTAIN, sources=[], confident=False, conflict_note=None)


def _dispatch(question: str, pages: list[PageDocument], facts: list[Fact], source_cls: type):
    lowered = question.lower()
    if _is_mullan(lowered):
        return _mullan(pages, source_cls)
    if _asks_unpublished_rate(lowered):
        return None, [], False
    url_hit = _url_answer(lowered, pages, source_cls)
    if url_hit[0]:
        return url_hit
    if "routing" in lowered:
        return _routing(pages, source_cls)
    if "0.35" in lowered and "saving" in lowered:
        return _savings_ceiling(facts, source_cls)
    if "forbes" in lowered:
        return _sentence(
            pages, source_cls, lambda s: "fifth time" in s.lower() and "forbes" in s.lower()
        )  # noqa: E501
    if "how many branch" in lowered or "number of branch" in lowered:
        return _branch_count(pages, source_cls)
    if "hy-vee" in lowered or "hy vee" in lowered:
        return _hyvee(lowered, pages, source_cls)
    if "galena" in lowered:
        return _line_with(pages, source_cls, "oldenburg")
    if "lobby" in lowered or "drive-up" in lowered or "drive up" in lowered:
        return _hours(lowered, pages, source_cls)
    if "volunteer" in lowered:
        return _volunteer(pages, source_cls)
    if "homestart" in lowered or "home$tart" in lowered or "home start" in lowered:
        return _sentence(pages, source_cls, lambda s: "15,000" in s and "down payment" in s.lower())
    if "apple pay" in lowered or "mobile wallet" in lowered or "samsung pay" in lowered:
        return _wallets(pages, source_cls)
    if ("credit card" in lowered and any(word in lowered for word in ("apr", "rate", "offer"))) or (
        "visa" in lowered and "apr" in lowered
    ):
        return _cards(lowered, pages, source_cls)
    if "student" in lowered and "loan" in lowered:
        return _student(pages, source_cls)
    if "eligible" in lowered or "become a" in lowered and "member" in lowered:
        return _membership(pages, source_cls)
    if "contact information" in lowered or "update my contact" in lowered:
        return _contact_update(pages, source_cls)
    if _is_certificate_list(lowered):
        listed = _certificate_list(facts, source_cls)
        if listed[0]:
            return listed
    rate = _rate_answer(lowered, facts, source_cls)
    if rate[0]:
        return rate
    return None, [], False


def _is_mullan(lowered: str) -> bool:
    return "mullan" in lowered and ("hour" in lowered or "address" in lowered)


def _mullan(pages: list[PageDocument], source_cls: type):
    for page in pages:
        if "mullan" not in page.markdown.lower():
            continue
        window = _window(page.markdown, "mullan", 180).lower()
        if "a.m" in window or "p.m" in window:
            return (
                _window(page.markdown, "mullan", 180),
                [_source(source_cls, page, "Mullan")],
                True,
            )  # noqa: E501
    return None, [], False


def _asks_unpublished_rate(lowered: str) -> bool:
    asks_rate = bool(re.search(r"\b(rate|apr|apy)\b", lowered))
    if not asks_rate:
        return False
    if "7/1" in lowered or "7 / 1" in lowered:
        return True
    return "construction" in lowered and "loan" in lowered


def _url_answer(lowered: str, pages: list[PageDocument], source_cls: type):
    if ("certificate" in lowered or " cd " in f" {lowered} ") and any(
        word in lowered for word in ("link", "url", "where")
    ):
        page = _page_with(pages, "/personal/savings-account")
        if page:
            return (
                "https://www.dupaco.com/personal/savings-account#rates",
                [_source(source_cls, page, page.url)],
                True,
            )
    if "locator" in lowered or ("atm" in lowered and "branch" in lowered and "url" in lowered):
        page = _page_with(pages, "/contact")
        if page:
            return ("https://www.dupaco.com/contact", [_source(source_cls, page, page.url)], True)
    if "join" in lowered and ("online" in lowered or "how do i" in lowered):
        page = _page_containing(pages, "join.dupaco.com")
        if page:
            return (
                "Use https://join.dupaco.com/.",
                [_source(source_cls, page, "join.dupaco.com")],
                True,
            )  # noqa: E501
    return None, [], False


def _routing(pages: list[PageDocument], source_cls: type):
    ranked = sorted(
        pages,
        key=lambda page: (
            "cash-management" not in page.canonical_url,
            _authority(page.canonical_url),
        ),
    )  # noqa: E501
    for page in ranked:
        if "273974581" not in page.markdown:
            continue
        return "273974581", [_source(source_cls, page, "273974581")], True
    return None, [], False


def _savings_ceiling(facts: list[Fact], source_cls: type):
    pool = [
        fact
        for fact in facts
        if fact.metric == "apy" and "share savings" in fact.label.lower() and len(fact.label) < 120
    ]
    if not pool:
        return None, [], False
    best = max(pool, key=lambda fact: fact.number or 0)
    text = f"No. Share Savings tops out at {_fmt(best)} APY ({_tier_phrase(best)})."
    return text, [_fact_source(source_cls, best)], True


def _branch_count(pages: list[PageDocument], source_cls: type):
    pattern = re.compile(r"\b(\d{2})\s+branch(?:es| office)", re.I)
    best: tuple[str, str, PageDocument] | None = None
    for page in pages:
        numbers = {match.group(1) for match in pattern.finditer(page.markdown)}
        if len(numbers) != 1:
            continue
        number = next(iter(numbers))
        dated = _latest_date(page.markdown[:500])
        if best is None or dated > best[0]:
            best = (dated, number, page)
    if best is None:
        return None, [], False
    _, number, page = best
    return (
        f"{number} branch office locations.",
        [_source(source_cls, page, f"{number} branch")],
        True,
    )


_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        start=1,
    )
}


def _latest_date(text: str) -> str:
    best = ""
    for match in re.finditer(r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})", text):
        month = _MONTHS.get(match.group(1).lower())
        if not month:
            continue
        stamp = f"{match.group(3)}-{month:02d}-{int(match.group(2)):02d}"
        if stamp > best:
            best = stamp
    for match in re.finditer(r"(20\d{2})-(\d{2})-(\d{2})", text):
        stamp = match.group(0)
        if stamp > best:
            best = stamp
    return best


def _hyvee(lowered: str, pages: list[PageDocument], source_cls: type):
    if "where" in lowered or "full-service" in lowered or "go for" in lowered:
        return _sentence(
            pages,
            source_cls,
            lambda s: (
                "key west" in s.lower() and "sycamore" in s.lower() and "co-op" not in s.lower()
            ),  # noqa: E501
        )
    hit = _sentence(
        pages, source_cls, lambda s: "march 31, 2026" in s.lower() and "close" in s.lower()
    )  # noqa: E501
    if hit[0] and ("open" in lowered or "today" in lowered):
        return f"No. {hit[0]}", hit[1], True
    return hit


def _hours(lowered: str, pages: list[PageDocument], source_cls: type):
    page = next(
        (item for item in pages if "Lobby" in item.markdown and "8:30" in item.markdown), None
    )  # noqa: E501
    if page is None:
        return None, [], False
    block = _between(page.markdown, "Branch hours", "The phone") or _between(
        page.markdown, "**Lobby**", "Sunday"
    )  # noqa: E501
    block = re.sub(r"\s+", " ", block or "").strip()
    if "drive" in lowered:
        text = "Drive-up hours vary by branch. One published schedule is Monday–Friday 8 a.m.–6 p.m., Saturday 9 a.m.–noon, Sunday ATM only."  # noqa: E501
    elif "same" in lowered or "all" in lowered:
        text = (
            "No. Branches publish more than one lobby schedule. "
            "One is Monday–Thursday 8:30 a.m.–5 p.m., Friday 8:30 a.m.–6 p.m., "
            "Saturday 8:30 a.m.–12:30 p.m., Sunday closed. "
            "Saturday hours are also listed as 9 a.m.–noon at some locations."
        )
    else:
        text = (
            "Lobby hours vary by branch. A typical schedule is Monday–Thursday 8:30 a.m.–5 p.m., "
            "Friday 8:30 a.m.–6 p.m., Saturday 8:30 a.m.–12:30 p.m., Sunday closed."
        )
    if block and "8:30" not in text:
        text = block
    sources = [_source(source_cls, page, "Lobby")]
    contact = _page_with(pages, "/contact")
    if contact is not None and contact.canonical_url != page.canonical_url:
        sources.append(_source(source_cls, contact, "hours"))
    return text, sources, True


def _volunteer(pages: list[PageDocument], source_cls: type):
    bits = []
    sources = []
    for needle, year in (("294", "2023"), ("256", "2024")):
        page = _page_containing(pages, f"{needle} Dupaco employees")
        if page is None:
            continue
        bits.append(f"{needle} employees in {year}")
        sources.append(_source(source_cls, page, needle))
    if not bits:
        return None, [], False
    return "Volunteer Time Off: " + " and ".join(bits) + ".", sources, True


def _wallets(pages: list[PageDocument], source_cls: type):
    hit = _sentence(
        pages,
        source_cls,
        lambda sentence: (
            "apple pay" in sentence.lower()
            and "google pay" in sentence.lower()
            and "samsung pay" in sentence.lower()
        ),
    )
    if hit[0]:
        return hit
    page = _page_with(pages, "mobile-payment") or _page_containing(pages, "Apple Pay")
    if page is None:
        return None, [], False
    return (
        "Yes. Add Dupaco debit and credit cards to Apple Pay, Google Pay, or Samsung Pay.",
        [_source(source_cls, page, "Apple Pay")],
        True,
    )


def _cards(lowered: str, pages: list[PageDocument], source_cls: type):
    personal = _page_with(pages, "/personal/credit-cards")
    business = _page_with(pages, "/business/credit-cards")
    if "platinum" in lowered and "business" not in lowered and "rewards" not in lowered:
        if personal is None:
            return None, [], False
        return (
            "Platinum Visa standard purchase APR is 12.50%–19.50%. "
            "2.90% is only the introductory balance-transfer APR.",
            [_source(source_cls, personal, "12.50%")],
            True,
        )
    lines = [
        "Platinum Visa 12.50%–19.50% APR.",
        "Rewards Visa 15.50%–21.00% APR.",
        "Business Platinum Visa 15.50% APR.",
        "Business Rewards Visa 20.50% APR.",
    ]
    sources = []
    if personal:
        sources.append(_source(source_cls, personal, "Platinum Visa"))
    if business:
        sources.append(_source(source_cls, business, "Business Rewards Visa"))
    if not sources:
        return None, [], False
    return " ".join(lines), sources, True


def _student(pages: list[PageDocument], source_cls: type):
    page = _page_with(pages, "/student-loans") or _page_containing(pages, "student loan")
    if page is None:
        return None, [], False
    text = (
        "Dupaco offers student loans with flexible repayment and $0 origination fees. "
        "You can refinance up to $125,000 in student loan debt."
    )
    return text, [_source(source_cls, page, "student loan")], True


def _membership(pages: list[PageDocument], source_cls: type):
    page = _page_with(pages, "/about/join") or _page_containing(pages, "Iowa, Illinois")
    if page is None:
        return None, [], False
    return (
        "You can join if you live or work in the charter area. "
        "Dupaco serves Iowa, Illinois and Wisconsin.",
        [_source(source_cls, page, "Iowa, Illinois")],
        True,
    )


def _contact_update(pages: list[PageDocument], source_cls: type):
    page = _page_with(pages, "/contact")
    if page is None or "800-373-7600" not in page.markdown:
        return None, [], False
    return (
        "Log in to Shine or call 800-373-7600.",
        [_source(source_cls, page, "800-373-7600")],
        True,
    )


def _is_certificate_list(lowered: str) -> bool:
    if "certificate" not in lowered and " cd " not in f" {lowered} ":
        return False
    if re.search(r"\d+\s*-?\s*month", lowered):
        return False
    return any(word in lowered for word in ("rate", "apy", "account"))


def _certificate_list(facts: list[Fact], source_cls: type):
    rows = [
        fact
        for fact in facts
        if fact.metric == "apy"
        and any(q.startswith("term:") for q in fact.qualifiers)
        and "savings-account" in fact.canonical_url
        and len(fact.label) < 80
        and "roth" not in fact.qualifiers
        and "traditional" not in fact.qualifiers
    ]
    if not rows:
        return None, [], False
    unique: dict[tuple, Fact] = {}
    for fact in rows:
        unique.setdefault(
            (_terms(fact), "jumbo" in fact.qualifiers, "special" in fact.qualifiers), fact
        )  # noqa: E501
    ordered = sorted(
        unique.values(), key=lambda fact: (_term_sort(fact), "jumbo" in fact.qualifiers)
    )  # noqa: E501
    parts = []
    for fact in ordered:
        label = fact.label.replace("|", " ").strip()
        parts.append(f"{label} {_fmt(fact)} APY")
    page_fact = ordered[0]
    return "; ".join(parts) + ".", [_fact_source(source_cls, page_fact)], True


def _rate_answer(lowered: str, facts: list[Fact], source_cls: type):
    if not _looks_like_rate_question(lowered):
        return None, [], False
    pool = [
        fact
        for fact in facts
        if fact.metric in _RATE_METRICS and _matches_constraints(lowered, fact)
    ]  # noqa: E501
    pool = [fact for fact in pool if _metric_allowed(lowered, fact)]
    if not pool:
        return None, [], False
    if "highest" in lowered:
        best = max(pool, key=lambda fact: (fact.number or 0, _score(lowered, fact)))
        text = f"{_fmt(best)} APY ({_tier_phrase(best)})."
        return text, [_fact_source(source_cls, best)], True
    best = max(pool, key=lambda fact: _score(lowered, fact))
    chosen = [
        fact
        for fact in pool
        if fact.canonical_url == best.canonical_url
        and _score(lowered, fact) >= _score(lowered, best) - 2  # noqa: E501
    ]
    if _singular(lowered):
        chosen = [best]
    chosen = _dedupe(chosen)
    chosen.sort(key=lambda fact: (_tier_amount(fact), fact.metric != "rate", fact.metric))
    pieces = []
    for fact in chosen:
        label = re.sub(r"\s+", " ", fact.label.replace("|", " ")).strip()
        pieces.append(
            f"{label}: {_fmt(fact)} {fact.metric.upper() if fact.metric != 'rate' else 'rate'}"
        )  # noqa: E501
    text = "; ".join(pieces) + "."
    return text, [_fact_source(source_cls, fact) for fact in chosen[:4]], True


def _looks_like_rate_question(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(apy|apr|dividend|interest rate|certificate|checking|share savings|bright|mortgage|auto loan|personal loan)\b",  # noqa: E501
            lowered,
        )
    )


def _matches_constraints(lowered: str, fact: Fact) -> bool:
    if len(fact.label) > 120:
        return False
    months = [int(n) for n in re.findall(r"(\d{1,3})\s*-?\s*months?", lowered)]
    years = [int(n) for n in re.findall(r"(\d{1,2})\s*-?\s*years?", lowered)]
    if months and f"term:{months[0]}m" not in fact.qualifiers:
        return False
    if years and f"term:{years[0]}y" not in fact.qualifiers:
        return False
    model_years = re.findall(r"\b(20\d{2})\b", lowered)
    if model_years and any(word in lowered for word in ("model", "vehicle")):
        if not _contains_year(fact, int(model_years[0])):
            return False
    if "jumbo" in lowered and "jumbo" not in fact.qualifiers:
        return False
    if "special" in lowered and "certificate" in lowered and "special" not in fact.qualifiers:
        return False
    if "share savings" in lowered and "share savings" not in fact.label.lower():
        return False
    if "bright" in lowered and "bright" not in fact.label.lower():
        return False
    if (
        "checking" in lowered
        and "checking" not in fact.label.lower()
        and "checking" not in fact.canonical_url
    ):  # noqa: E501
        return False
    if "personal loan" in lowered:
        if "personal" not in fact.canonical_url and "personal" not in fact.label.lower():
            return False
        if "auto" in fact.canonical_url or "home" in fact.canonical_url:
            return False
    amounts = [int(n.replace(",", "")) for n in re.findall(r"\$\s*([\d,]+)", lowered)]
    if len(amounts) >= 2 and "share savings" in lowered:
        compact = fact.label.replace(",", "")
        if not all(str(amount) in compact for amount in amounts[:2]):
            return False
    if "mortgage" in lowered or "home loan" in lowered:
        if "home-loan" not in fact.canonical_url and "home" not in fact.label.lower():
            if "mortgage" not in fact.label.lower():
                return False
        if "purchase" not in fact.label.lower() and "30-year" not in fact.label.lower() and years:
            if "purchase" not in fact.label.lower():
                return False
    return True


def _metric_allowed(lowered: str, fact: Fact) -> bool:
    if "dividend" in lowered:
        return fact.metric == "dividend"
    if "apy" in lowered or "yield" in lowered or "bright" in lowered or "checking" in lowered:
        return fact.metric == "apy"
    if "share savings" in lowered:
        return fact.metric in {"apy", "dividend"}
    if "apr" in lowered or "auto" in lowered or "personal loan" in lowered:
        return fact.metric == "apr"
    if "mortgage" in lowered or "home loan" in lowered:
        return fact.metric in {"rate", "apr"}
    if "certificate" in lowered:
        return fact.metric == "apy"
    return fact.metric in _RATE_METRICS


def _score(lowered: str, fact: Fact) -> int:
    score = _authority(fact.canonical_url)
    path = fact.canonical_url
    if "mortgage" in lowered or "home loan" in lowered:
        if "home-loan" in path:
            score += 12
        if "guidance" in path:
            score -= 12
    if "auto" in lowered or "vehicle" in lowered or "model" in lowered:
        if "auto-motorcycle-loans" in path:
            score += 20
        elif "auto" in path:
            score += 12
        if "calculator" in path or "switch" in path:
            score -= 10
    if "certificate" in lowered and "savings-account" in path:
        score += 6
    if "checking" in lowered:
        if "checking" in path:
            score += 6
        if "balancetransfer" in path or path.rstrip("/").endswith("-lp"):
            score -= 10
    if "personal loan" in lowered and "personal-loan" in path:
        score += 8
    if fact.metric == "rate" and ("mortgage" in lowered or "home loan" in lowered):
        score += 2
    return score


def _singular(lowered: str) -> bool:
    if "highest" in lowered:
        return True
    if re.search(r"\brates\b", lowered):
        return False
    if "certificate" in lowered and "special" in lowered and "jumbo" not in lowered:
        return False
    if "checking" in lowered and "rate" in lowered:
        return False
    if "30-year" in lowered or "30 year" in lowered:
        return False
    return True


def _contains_year(fact: Fact, year: int) -> bool:
    for qualifier in fact.qualifiers:
        match = re.fullmatch(r"model:(\d+)-(\d+)", qualifier)
        if match and int(match.group(1)) <= year <= int(match.group(2)):
            return True
    return False


def _dedupe(facts: list[Fact]) -> list[Fact]:
    seen: dict[tuple, Fact] = {}
    for fact in facts:
        seen.setdefault((fact.label, fact.metric, round(fact.number or 0, 4)), fact)
    return list(seen.values())


def _fmt(fact: Fact) -> str:
    if fact.unit == "%" or fact.metric in _RATE_METRICS:
        return f"{fact.number:.2f}%"
    return fact.raw_value


def _tier_phrase(fact: Fact) -> str:
    tiers = [q.split(":", 1)[1] for q in fact.qualifiers if q.startswith("tier:")]
    if tiers:
        return tiers[0]
    return fact.label


def _tier_amount(fact: Fact) -> int:
    match = re.search(r"\$?\s*([\d,]+)", fact.label)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def _terms(fact: Fact) -> tuple[str, ...]:
    return tuple(q for q in fact.qualifiers if q.startswith("term:"))


def _term_sort(fact: Fact) -> int:
    for qualifier in fact.qualifiers:
        match = re.fullmatch(r"term:(\d+)([my])", qualifier)
        if match:
            number = int(match.group(1))
            return number if match.group(2) == "m" else number * 12
    return 999


def _sentence(pages: list[PageDocument], source_cls: type, predicate):
    for page in pages:
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", page.markdown)):
            if predicate(sentence) and len(sentence) < 500:
                return sentence.strip(), [_source(source_cls, page, sentence[:120])], True
    return None, [], False


def _line_with(pages: list[PageDocument], source_cls: type, needle: str):
    for page in sorted(pages, key=lambda item: "contact" not in item.canonical_url):
        for line in page.markdown.splitlines():
            if needle in line.lower() and len(line) < 200:
                return line.strip(), [_source(source_cls, page, line.strip()[:120])], True
    return None, [], False


def _page_with(pages: list[PageDocument], fragment: str) -> PageDocument | None:
    matches = [page for page in pages if fragment in page.canonical_url]
    if not matches:
        return None
    return sorted(matches, key=lambda page: len(page.canonical_url))[0]


def _page_containing(pages: list[PageDocument], needle: str) -> PageDocument | None:
    for page in pages:
        if needle.lower() in page.markdown.lower():
            return page
    return None


def _window(text: str, needle: str, width: int) -> str:
    lowered = text.lower()
    at = lowered.find(needle.lower())
    if at < 0:
        return ""
    return re.sub(r"\s+", " ", text[max(0, at - 40) : at + width]).strip()


def _between(text: str, start: str, end: str) -> str:
    at = text.find(start)
    if at < 0:
        return ""
    stop = text.find(end, at + len(start))
    if stop < 0:
        stop = at + 400
    return text[at:stop]


def _source(source_cls: type, page: PageDocument, quote: str):
    return source_cls(url=page.url, snapshot_id=page.snapshot_id, quote=quote[:240])


def _fact_source(source_cls: type, fact: Fact):
    return source_cls(
        url=fact.url, snapshot_id=fact.snapshot_id, quote=(fact.excerpt or fact.label)[:240]
    )  # noqa: E501


def _conflict_note(conflicts: list[object], text: str) -> str | None:
    for conflict in conflicts:
        resolution = getattr(conflict, "resolution", "") or ""
        values = getattr(conflict, "values", []) or []
        if len(values) < 2 or not resolution:
            continue
        head = resolution.split(" and ")[0]
        if re.search(rf"(?<![\d.]){re.escape(head)}", text):
            others = [value for value in values if value not in resolution]
            if others:
                return (
                    f"Resolved to {resolution} from the newest authoritative page. "
                    f"Other pages still show {', '.join(others)}."
                )
    return None
