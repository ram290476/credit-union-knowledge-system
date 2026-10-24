# Project process and memory

Imported on 2026-10-24 from [ram290476/investor-dashboard](https://github.com/ram290476/investor-dashboard).

## Sources

| Source (investor-dashboard) | Copied to | Notes |
|---|---|---|
| `AGENTS.md` (added by PR #310, closing issue #309) | `AGENTS.md` | Full text, adapted only where tied to the investor dashboard. Adapted spots are marked "(adapted from investor-dashboard)". |
| `docs/operations.md`, section "GitHub Actions CI/CD" | `docs/process/ci-cd-deploy-gate.md` | Verbatim reference for the CI `validate` / Deploy production / Terraform destroy gate that the standard workflow relies on. Applies here once deploy infra exists. |

## Current state of this repo (2026-10-24)

- No CI workflow (`.github/workflows/`) exists yet, so there is no `validate` job. PRs are squash-merged after review until CI is added.
- No deploy workflow or Terraform exists yet, so the post-merge deploy destroy check applies once deploy infra exists.

## Local additions

- 2026-10-24: Added the wiki-update rule to `AGENTS.md` (steps 2 and 6 of the standard workflow). Local addition, not from investor-dashboard. Same day, step 6 was amended to require screenshots committed into the wiki repo and embedded inline with relative links, not external URLs.

## Project context

Knowledge system over five credit union website snapshots: Q&A with citations, conflict resolution and abstention.
