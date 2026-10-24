# Build Log: Credit Union Knowledge System

## Challenge
Build a knowledge system that knows what's true *now*. Input: five snapshots of a credit union's website. The system must answer questions accurately, resolve conflicting information across snapshots, cite its sources, and recognise when an answer isn't available. Kit includes requirements PDF, snapshots, practice questions, starter code and scoring tools. Deliverable: solution code in a public GitHub repo.

## Done so far (2026-10-24, PT)
- **Repo setup:** created public repo `ram290476/credit-union-knowledge-system` with an initial README.
- **Cloud coding environment:** launched a Cursor cloud coding agent on a Cursor-managed Linux VM ([agent](https://cursor.com/agents/bc-1f8c6c8f-dca4-5edb-a673-3d21abc4824a)) with the assignment PDF and participant kit. It works on a branch and delivers via pull request.
- **Docs scaffolding:** this Build Log, build-log issue #1, and work-item issues #2 (ingestion), #3 (conflict resolution), #4 (answer generation), #5 (evaluation). The wiki is enabled, but GitHub only creates the wiki repo once a first page is saved in the web UI, so this log lives at `docs/BUILD_LOG.md`.

## Plan going forward
1. Snapshot ingestion: parse the five snapshots into dated, page-level documents with source metadata.
2. Conflict resolution: detect facts that differ across snapshots and prefer the most recent authoritative source, recording why.
3. Answer generation: retrieve, answer with citations (snapshot + page), and abstain when unsupported.
4. Evaluation: run the kit's scoring tools on practice questions and iterate.
5. Docs: README with setup, architecture, decisions and score.

Each major work item gets its own GitHub issue; this page is updated as work progresses.

## Decision log
| Date | Decision | Why |
|---|---|---|
| 2026-10-24 | Use a cloud coding agent + PR workflow | Reproducible, reviewable history |
