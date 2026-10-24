"""Turn page markdown into passages and qualified numeric facts.

Tables keep each tier on its own row. A percent is tagged from the column
header when there is one (APY vs APR vs dividend vs rate) and otherwise from
the words next to the number. This module does not decide which value wins.
"""

from __future__ import annotations

import re

from knowledge.models import ParsedFact, ParsedPassage, ParseResult

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
MONEY_RE = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
TERM_MONTH_RE = re.compile(r"\b(\d{1,3})\s*[- ]?\s*months?\b", re.I)
TERM_YEAR_RE = re.compile(r"\b(\d{1,2})\s*[- ]?\s*years?\b", re.I)
MODEL_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\s*[-–—]\s*(\d{2,4})\b")
TIER_RE = re.compile(
    r"(\$\s*[\d,]+(?:\.\d+)?\s*(?:[-–—]|to)\s*\$\s*[\d,]+(?:\.\d+)?|\$\s*[\d,]+(?:\.\d+)?\s*\+)",
    re.I,
)
PRODUCT_WORDS = (
    "certificate",
    "savings",
    "checking",
    "mortgage",
    "auto",
    "visa",
    "loan",
    "ira",
)
MAX_LINE = 5000
MAX_PASSAGE = 1500
MAX_PROSE_FACT = 500
MAX_FACTS_PER_PAGE = 2000


def parse_markdown(markdown: str) -> ParseResult:
    text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    result = ParseResult()
    section = ""
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        body = "\n".join(paragraph).strip()
        paragraph = []
        if not body or "data:image" in body or len(body) > 8000:
            return
        if len(body) >= 40:
            result.passages.append(ParsedPassage(section, body[:MAX_PASSAGE], "prose"))
        _collect_prose_facts(result, section, body)

    i = 0
    while i < len(lines):
        line = lines[i]
        if len(line) > MAX_LINE:
            flush_paragraph()
            i += 1
            continue
        heading = HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            section = _clean(heading.group(2))
            if section:
                result.headings.append(section)
            i += 1
            continue
        if _is_table_start(lines, i):
            flush_paragraph()
            table_lines, i = _consume_table(lines, i)
            _add_table(result, section, table_lines)
            continue
        if not line.strip():
            flush_paragraph()
            i += 1
            continue
        paragraph.append(line)
        i += 1
    flush_paragraph()
    if len(result.facts) > MAX_FACTS_PER_PAGE:
        result.facts = result.facts[:MAX_FACTS_PER_PAGE]
    return result


def _add_table(result: ParseResult, section: str, table_lines: list[str]) -> None:
    raw = "\n".join(table_lines).strip()
    if raw:
        result.passages.append(ParsedPassage(section, raw[:MAX_PASSAGE], "table"))
    if len(table_lines) < 3:
        return
    headers = _split_row(table_lines[0]) or []
    for raw_row in table_lines[2:]:
        row = _split_row(raw_row)
        if not row:
            continue
        label_parts: list[str] = []
        values: list[tuple[str, str]] = []
        for idx, cell in enumerate(row):
            header = headers[idx] if idx < len(headers) else ""
            # Balance tiers are qualifiers of the rate, not a second rate.
            if _is_tier_cell(header, cell):
                if cell:
                    label_parts.append(cell)
                continue
            if _is_value_cell(cell):
                values.append((header, cell))
            elif cell:
                label_parts.append(cell)
        label = " | ".join(label_parts) or section or "row"
        context = f"{section} {label}".strip()
        for header, cell in values:
            if len(result.facts) >= MAX_FACTS_PER_PAGE:
                return
            metric = _metric_from_header(header) if header else _metric_from_text(cell)
            number, unit = _first_number(cell, metric)
            raw_value = _strip_percent_footnote(cell)
            excerpt = f"{label} | {header}: {raw_value}".strip(" |")
            result.facts.append(
                ParsedFact(
                    section=section,
                    label=label,
                    metric=metric,
                    raw_value=raw_value,
                    number=number,
                    unit=unit,
                    qualifiers=_qualifiers(context),
                    excerpt=excerpt[:300],
                    template=_template(section, label, metric),
                )
            )


def _collect_prose_facts(result: ParseResult, section: str, body: str) -> None:
    chunks = [body] if len(body) <= MAX_PROSE_FACT else re.split(r"(?<=[.!?])\s+", body)
    for chunk in chunks:
        piece = chunk.strip()
        if not piece or len(piece) > MAX_PROSE_FACT or len(piece) > MAX_LINE:
            continue
        if "data:image" in piece:
            continue
        context = f"{section} {piece}".strip()
        qualifiers = _qualifiers(context)
        seen: set[tuple[str, str]] = set()
        for match in PERCENT_RE.finditer(piece):
            if len(result.facts) >= MAX_FACTS_PER_PAGE:
                return
            raw_value = _strip_percent_footnote(match.group(0))
            key = ("%", raw_value)
            if key in seen:
                continue
            seen.add(key)
            metric = _metric_near(piece, match.start())
            number, unit = _first_number(raw_value, metric)
            result.facts.append(
                ParsedFact(
                    section=section,
                    label=_clean(piece)[:300],
                    metric=metric,
                    raw_value=raw_value,
                    number=number,
                    unit=unit or "%",
                    qualifiers=qualifiers,
                    excerpt=_clean(piece)[:300],
                    template=_template(section, piece, metric),
                )
            )
        if re.search(r"\b(fee|charge)\b", piece, re.I):
            for match in MONEY_RE.finditer(piece):
                if len(result.facts) >= MAX_FACTS_PER_PAGE:
                    return
                raw_value = re.sub(r"\s+", "", match.group(0))
                key = ("$", raw_value)
                if key in seen:
                    continue
                seen.add(key)
                number, unit = _first_number(raw_value, "fee")
                result.facts.append(
                    ParsedFact(
                        section=section,
                        label=_clean(piece)[:300],
                        metric="fee",
                        raw_value=raw_value,
                        number=number,
                        unit=unit or "$",
                        qualifiers=qualifiers,
                        excerpt=_clean(piece)[:300],
                        template=_template(section, piece, "fee"),
                    )
                )


def _qualifiers(text: str) -> tuple[str, ...]:
    found: list[str] = []
    lowered = text.lower()
    for match in TERM_MONTH_RE.finditer(lowered):
        found.append(f"term:{int(match.group(1))}m")
    for match in TERM_YEAR_RE.finditer(lowered):
        found.append(f"term:{int(match.group(1))}y")
    for match in MODEL_YEAR_RE.finditer(text):
        start = int(match.group(1))
        end_raw = match.group(2)
        if len(end_raw) == 4:
            end = int(end_raw)
        else:
            end = (start // 100) * 100 + int(end_raw)
            if end < start:
                end += 100
        found.append(f"model:{start}-{end}")
    tier = TIER_RE.search(text)
    if tier:
        compact = re.sub(r"\s+", "", tier.group(1))
        compact = compact.replace("–", "-").replace("—", "-").replace(",", "").lower()
        found.append(f"tier:{compact}")
    if "jumbo" in lowered:
        found.append("jumbo")
    if "special" in lowered:
        found.append("special")
    if re.search(r"illustrative|for example|if you borrow", lowered):
        found.append("example")
    for word in PRODUCT_WORDS:
        if re.search(rf"\b{word}\b", lowered):
            found.append(f"product:{word}")
    return tuple(dict.fromkeys(found))


def _metric_from_header(header: str) -> str:
    return _metric_from_text(header)


def _metric_from_text(text: str) -> str:
    lowered = text.lower()
    if "apy" in lowered or "annual percentage yield" in lowered or "yield" in lowered:
        return "apy"
    if "apr" in lowered or "annual percentage rate" in lowered:
        return "apr"
    if "dividend" in lowered:
        return "dividend"
    if "fee" in lowered or "charge" in lowered:
        return "fee"
    if "payment" in lowered:
        return "payment"
    if "point" in lowered:
        return "points"
    if "minimum" in lowered or re.search(r"\bmin\b", lowered):
        return "minimum"
    if "balance" in lowered or "tier" in lowered:
        return "tier"
    if re.search(r"\brate\b", lowered):
        return "rate"
    if "$" in text:
        return "amount"
    if "%" in text:
        return "percent"
    return "value"


def _metric_near(text: str, start: int) -> str:
    window = text[max(0, start - 48) : start + 12]
    metric = _metric_from_text(window)
    if metric in {"percent", "amount", "value"}:
        return _metric_from_text(text)
    return metric


def _first_number(raw: str, metric: str) -> tuple[float | None, str]:
    if metric in {"fee", "minimum", "amount", "payment", "tier"} or ("$" in raw and "%" not in raw):
        match = re.search(r"\$?\s*(\d[\d,]*(?:\.\d+)?)", raw)
        if match and "$" in raw:
            return float(match.group(1).replace(",", "")), "$"
    match = PERCENT_RE.search(raw)
    if match:
        number = re.search(r"\d+(?:\.\d+)?", match.group(0))
        return (float(number.group(0)) if number else None), "%"
    match = re.search(r"\d+(?:\.\d+)?", raw)
    if match:
        return float(match.group(0).replace(",", "")), ""
    return None, ""


def _template(section: str, label: str, metric: str) -> str:
    text = f"{section} | {label} | {metric}"
    text = PERCENT_RE.sub("{pct}", text)
    text = MONEY_RE.sub("{amt}", text)
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def _is_tier_cell(header: str, cell: str) -> bool:
    if header and _metric_from_header(header) == "tier":
        return True
    return TIER_RE.search(cell) is not None


def _is_value_cell(cell: str) -> bool:
    if PERCENT_RE.search(cell) or MONEY_RE.search(cell):
        return True
    stripped = cell.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", stripped):
        number = float(stripped)
        if stripped.isdigit() and 1900 <= number <= 2100:
            return False
        return True
    return False


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    if "|" not in lines[index] or len(lines[index]) > MAX_LINE:
        return False
    return _is_separator(lines[index + 1])


def _consume_table(lines: list[str], index: int) -> tuple[list[str], int]:
    table = [lines[index], lines[index + 1]]
    cursor = index + 2
    while cursor < len(lines):
        line = lines[cursor]
        if len(line) > MAX_LINE or "|" not in line or not line.strip():
            break
        table.append(line)
        cursor += 1
    return table, cursor


def _is_separator(line: str) -> bool:
    cells = _split_row(line)
    if not cells:
        return False
    return all(SEPARATOR_CELL_RE.match(cell.replace(" ", "")) for cell in cells)


def _split_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if "|" not in stripped:
        return None
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [_clean(cell) for cell in stripped.split("|")]


def _clean(value: str) -> str:
    text = value.replace("\\r\\n", " ").replace("\u00a0", " ")
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text).strip()
    return _strip_percent_footnote(text)


def _strip_percent_footnote(value: str) -> str:
    return re.sub(r"%\d+\b", "%", value)
