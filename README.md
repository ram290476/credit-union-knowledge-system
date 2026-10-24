# Credit union knowledge system

A Python knowledge system that reads dated snapshots of a credit union website and, once the later pieces land, answers member questions from what was true at the time. This repository currently implements **snapshot ingestion** ([issue #2](https://github.com/ram290476/credit-union-knowledge-system/issues/2)).

Conflict resolution ([#3](https://github.com/ram290476/credit-union-knowledge-system/issues/3)), answer generation ([#4](https://github.com/ram290476/credit-union-knowledge-system/issues/4)), and practice-set scoring ([#5](https://github.com/ram290476/credit-union-knowledge-system/issues/5)) are separate changes. Until those land, `answer()` abstains and `conflicts()` is empty.

Design notes live on the [wiki](https://github.com/ram290476/credit-union-knowledge-system/wiki/Home). The running log is the [Build Log](https://github.com/ram290476/credit-union-knowledge-system/wiki/Build-Log).

## Contract

`solution.py` exposes `build()`. The returned object implements the harness protocol:

| Method | Status |
|---|---|
| `ingest(snapshot)` | Implemented. Stores every page, passage, and qualified fact with its snapshot id, date, URL, and fetch time. |
| `answer(question, as_of=None)` | Stub. Abstains with no digits so the protocol stays callable. |
| `conflicts()` | Stub. Returns an empty list. |

The scorer passes `Snapshot` / `Page` objects from `harness/contract.py`. Ingestion only reads attributes (`snapshot_id`, `taken_on`, `pages`, `url`, `title`, `markdown`, `fetched_at`), so it does not import the harness.

## What ingestion stores

For each snapshot, oldest first:

- A page document: original URL, canonical URL, title, markdown, `fetched_at`, content hash, headings.
- Passages under the heading they came from (prose paragraphs and markdown tables).
- Facts from table cells and short prose: metric (`apy`, `apr`, `dividend`, `rate`, `fee`, and the other column kinds), numeric value, unit, and qualifiers (term, model-year window, balance tier, jumbo, special, product word).
- Added, removed, changed, and unchanged canonical URLs versus the previous snapshot by date.

`snapshot_as_of(date)` returns the latest snapshot with `taken_on` on or before that date. `None` means the newest snapshot. `answer()` does not use that choice yet.

Tiers stay on separate rows. APY and APR from the same row stay separate facts. The loader does not call the live website.

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
| `knowledge/system.py` | `ingest`, plus the answer and conflict stubs |
| `knowledge/store.py` | Versioned store and as-of lookup |
| `knowledge/parse.py` | Markdown passages and qualified facts |
| `knowledge/snapshot_loader.py` | Read `manifest.json` + `pages/*.md` for the smoke run |
| `scripts/smoke_snapshots.py` | Five-snapshot smoke |
| `tests/fixtures/snapshots/` | Synthetic snapshots used in CI |

See `NOTES.md` for the ingestion decisions.
