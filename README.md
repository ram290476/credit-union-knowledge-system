# Credit union knowledge system

A Python knowledge system that reads dated snapshots of a credit union website and answers member questions from what was true at the time. This repository implements snapshot ingestion ([issue #2](https://github.com/ram290476/credit-union-knowledge-system/issues/2)), conflict resolution ([issue #3](https://github.com/ram290476/credit-union-knowledge-system/issues/3)), and answers with citations or abstention ([issue #4](https://github.com/ram290476/credit-union-knowledge-system/issues/4)). The practice-question score is [0.969](#practice-score) ([issue #5](https://github.com/ram290476/credit-union-knowledge-system/issues/5)).

Design notes live on the [wiki](https://github.com/ram290476/credit-union-knowledge-system/wiki/Home). The running log is the [Build Log](https://github.com/ram290476/credit-union-knowledge-system/wiki/Build-Log).

## Contract

`solution.py` exposes `build()`. The returned object implements the harness protocol:

| Method | Status |
|---|---|
| `ingest(snapshot)` | Implemented. Stores every page, passage, and qualified fact with its snapshot id, date, URL, and fetch time. |
| `answer(question, as_of=None)` | Implemented. Answers from the snapshot in effect on that date, cites the page, and abstains with no digits when the snapshot does not say. |
| `conflicts()` | Implemented. Returns disagreeing facts, the winning value, and why. |

The scorer passes `Snapshot` / `Page` objects from `harness/contract.py`. Ingestion only reads attributes (`snapshot_id`, `taken_on`, `pages`, `url`, `title`, `markdown`, `fetched_at`), so it does not import the harness.

## What ingestion stores

For each snapshot, oldest first:

- A page document: original URL, canonical URL, title, markdown, `fetched_at`, content hash, headings.
- Passages under the heading they came from (prose paragraphs and markdown tables).
- Facts from table cells and short prose: metric (`apy`, `apr`, `dividend`, `rate`, `fee`, and the other column kinds), numeric value, unit, and qualifiers (term, model-year window, balance tier, jumbo, special, product word).
- Added, removed, changed, and unchanged canonical URLs versus the previous snapshot by date.

`snapshot_as_of(date)` returns the latest snapshot with `taken_on` on or before that date. `None` means the newest snapshot. `answer()` uses that snapshot and does not read later pages.

Tiers stay on separate rows. APY and APR from the same row stay separate facts. The loader does not call the live website.

## Conflicts

`conflicts()` groups facts that name the same metric, term, balance tier, and model-year window but not the same number. A cell that says APR is an APR even when the column header says yield. Shifted model-year windows that mostly overlap (for example 2023–2026 and 2024–2027 on a 60-month term) are one group. Different tiers, APY versus APR, and illustrative examples are not conflicts.

The winning value is the one on the newest snapshot's highest-authority page. Paths that look like rate or fee sheets outrank calculators, promos, news, and blogs. Each conflict includes the competing values, a source for each value, the resolution, and a short reason.

## Answers

`answer(question, as_of)` reads only the snapshot selected by `as_of`. Rate questions use the qualified facts and prefer the official product page (auto loans, home loans, savings, checking) over a calculator or promo, so a stale table on the same crawl does not replace the rate sheet. A question that names a term, model year, jumbo flag, or balance tier keeps those constraints, which is what separates two savings tiers and two model-year windows.

Other questions quote a short passage from that snapshot: routing number, branch hours, addresses, Forbes recognition, Hy-Vee closure, membership, and similar facts. If the snapshot does not state the requested rate or hours, the answer is an abstention with `confident=False` and no digits. Sources carry the page URL, snapshot id, and a short quote.

## Setup

Python 3.9 or newer. Graded runs use 3.11. There are no runtime dependencies and no API keys.

```bash
python -m pip install -r requirements-dev.txt   # ruff, for local lint
python -m unittest discover -s tests -v
python scripts/smoke_snapshots.py
```

The smoke command ingests five synthetic snapshots under `tests/fixtures/snapshots/`. They use the same snapshot ids and dates as the participant kit and contain invented pages, not the credit union site.

To smoke the real kit after you unpack it locally (the site download is not committed; the assignment says not to redistribute it):

```bash
python scripts/smoke_snapshots.py \
  --snapshots /path/to/kit/snapshots \
  --min-facts 500
```

Continuous integration is the `validate` workflow: ruff, unit tests, and the five-snapshot fixture smoke.

## Layout

| Path | Role |
|---|---|
| `solution.py` | `build()` entry point the scorer imports |
| `knowledge/system.py` | `ingest`, `conflicts`, and `answer` |
| `knowledge/conflicts.py` | Group disagreeing facts and pick the winning value |
| `knowledge/answer.py` | Citations, as-of filtering, and abstention |
| `knowledge/store.py` | Versioned store and as-of lookup |
| `knowledge/parse.py` | Markdown passages and qualified facts |
| `knowledge/snapshot_loader.py` | Read `manifest.json` + `pages/*.md` for the smoke run |
| `scripts/smoke_snapshots.py` | Five-snapshot smoke |
| `tests/fixtures/snapshots/` | Synthetic snapshots used in CI |

See `NOTES.md` for the ingestion, conflict, and answer decisions.

## Practice score

The participant kit is not in this repository. From a checkout, with the kit unpacked on disk and no API key set:

```bash
python /path/to/kit/harness/run_eval.py \
  --submission . \
  --snapshots /path/to/kit/snapshots \
  --eval /path/to/kit/eval/public_eval.jsonl \
  --out /tmp/eval-out
```

Recorded on 2026-10-24 with that command (Python 3, `ANTHROPIC_API_KEY` unset):

| Measure | Result |
|---|---|
| Questions | 40 |
| `qa_score` / `final_score` | 0.969 |
| Stale-trap hits | 0 |
| Errors | 0 |
| Consistency | 1.0 (20 paraphrase groups, 20 repeats) |
| Speed | p95 0.15 s, score 1.0 |
| Ingest | 7.5 s (limit 30 minutes; ingest is not part of the speed score) |

The public file does not include a conflicts gold set, so that pillar is omitted and the remaining weights are renormalized. Every public category scored 1.00 except `list_completeness` at 0.75.

The miss is `dup-005` (weight 2.0). Its `must_include` list is empty, and `scoring.py` records correctness 0 for an empty list unless the optional judge runs. The answer still lists the certificate APYs from the latest snapshot and does not ask which term the member wants (`must_not_include` is the phrase "Which certificate term would you like"). Setting `ANTHROPIC_API_KEY` lets the kit scorer call its judge; this repository never calls a model. No practice answers are hard-coded.
