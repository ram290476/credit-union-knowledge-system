# AGENTS.md

Guidance for people and coding agents working on credit-union-knowledge-system. (adapted from investor-dashboard: project name)

This project is a knowledge system over five credit union website snapshots: question answering with citations, conflict resolution between sources, and abstention when the snapshots do not support an answer. (adapted from investor-dashboard: project context)

## Standard workflow for any new work

1. **Issue first.** Create a GitHub issue describing the work before any code changes.
2. **Link the wiki.** If the issue relates to an existing wiki page, update that wiki page to reference the new issue (link it, for example `#123`).
3. **Implement against the issue.** Do the work (via a coding agent) on a branch, and open a PR that links the issue (for example `Closes #123`).
4. **Wait for CI.** Wait for the `validate` job to pass. (adapted from investor-dashboard: this repo has no CI workflow yet as of 2026-10-24; until a `validate` job exists, state in the PR that no CI ran, and add a `validate` job when CI is introduced.)
5. **Squash-merge.** Once `validate` passes, squash-merge the PR (`gh pr merge --squash`). Do not rely on GitHub auto-merge: the repo has no required checks, so auto-merge would merge immediately.
   - **Merge checklist:** Refuse to merge a pull request whose linked issue body is still a placeholder. Flesh out the issue and get the user's approval first (see "Issue as source of truth").
6. **Update the wiki with the fix.** Once the issue is fixed (merged), update the related wiki page again with screenshots showing the fix, embedded in the wiki page itself: commit the image files into the wiki repo (for example an `images/` folder in the `.wiki.git` repo) and render them inline with relative markdown image links (for example `![Fix](images/issue-123-after.png)`). Do not link to external URLs such as `raw.githubusercontent.com`.
7. **Deploy destroy check.** Merging to `main` automatically triggers the "Deploy production" workflow. After the merge, check the Terraform `Plan:` line in the deploy. If it would destroy or replace any resource, cancel the deploy immediately and report back instead of letting it proceed. A normal plan shows `0 to destroy`. (adapted from investor-dashboard: this repo has no deploy workflow or Terraform yet; the rule applies once deploy infra exists.)

## Issue as source of truth

- **Acceptance criteria first.** Every coding issue must carry its own acceptance criteria before implementation begins: what "done" looks like, inputs and outputs, edge cases, and how the work gets verified.
- **No code on a placeholder.** If an issue body is just a placeholder, flesh it out first and wait for the user's approval before writing any code.
- **Where each record lives.** The issue is the source of truth for the work item, alongside the wiki and the build log. The wiki explains the system, the build log records what happened, and the issue defines what this piece of work must do.

## Related rules

- Changes apply to every credit union snapshot. Do not hard-code a single credit union. (adapted from investor-dashboard: originally "Changes apply to every watchlist ticker. Do not hard-code tickers.")
- Never run a local `terraform apply`. (applies once Terraform infra exists)
- Embed PR screenshots with `raw.githubusercontent.com` URLs.
- In the later sections of `apps/web/styles.css`, use `rgb()` or CSS variables instead of `#` hex colors, because the tests reject hex colors there. (investor-dashboard-specific; kept for reference, applies only if this repo adopts the same web app layout and test)

See `docs/process/README.md` for where this came from and `docs/process/ci-cd-deploy-gate.md` for the source CI/CD and destroy-gate notes.
