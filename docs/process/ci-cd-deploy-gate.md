# CI/CD and deploy destroy gate (reference)

> Copied verbatim on 2026-10-24 from investor-dashboard `docs/operations.md`, section "GitHub Actions CI/CD". (adapted from investor-dashboard) It describes investor-dashboard infrastructure (AWS, Terraform, `invdash` names). credit-union-knowledge-system has no CI, deploy workflow or Terraform yet; keep these rules and apply them once deploy infra exists.

## GitHub Actions CI/CD

`.github/workflows/ci.yml` runs Python lint/tests, dependency audit, browser-JavaScript syntax
validation, Terraform format/validation, deploy-guard shell tests, an arm64 Lambda image build
and Checkov. It runs on pull requests and pushes to `main`.

`.github/workflows/deploy.yml` runs only after a successful `main` CI push, or by manual
dispatch from `main`. A manual run honors the `production` environment variable
`DEPLOY_ALLOW_DESTROY` only when that value is exactly `true`. Leave the variable unset.
An automatic run after CI ignores it even if it is still set. Protect the GitHub
`production` environment with required reviewers and branch restrictions; the environment gate
is what prevents an unreviewed production apply.
Configure:

### One-time setup

1. **Create the deploy role (administrator, once).** Terraform's `github_deploy` module creates
   three things:
   - the account's GitHub OIDC provider (`token.actions.githubusercontent.com`, audience
     `sts.amazonaws.com`);
   - the `invdash-terraform-deploy` role;
   - the `invdash-workload-boundary` permissions boundary, set on every `invdash-*` role.

   Apply it from a workstation signed in with AdministratorAccess; CI can't create its own role.
   If the account already has a GitHub OIDC provider, set `github_oidc_provider_arn` instead of
   creating a second one.
2. **Protect the environment.** In GitHub, open Settings → Environments → `production`.
   - Add **required reviewers** (Ram). This approval is the only human gate before
     `terraform apply -auto-approve` runs in CI.
   - Set deployment branches to **`main` only**.
3. **Add these values to the `production` environment** (environment-level, not repository-level):

| Name | Kind | Value and where it comes from |
| --- | --- | --- |
| `AWS_REGION` | Variable | `us-west-1` (must match Terraform `region`). |
| `AWS_DEPLOY_ROLE_ARN` | Secret | `terraform output -raw github_deploy_role_arn`, i.e. `arn:aws:iam::308639168050:role/invdash-terraform-deploy`. |
| `TF_BACKEND_CONFIG` | Secret | The full contents of the local `infra/terraform/backend.tf` (the `backend "s3"` block for bucket `invdash-tfstate-308639168050`, key `investor-dashboard/infra.tfstate`, region `us-west-1`, `encrypt = true`, `use_lockfile = true`). |
| `TERRAFORM_TFVARS` | Secret | The full contents of the local `infra/terraform/terraform.tfvars`, **plus** `sec_user_agent = "investor-dashboard <contact email>"`. Leave out `jobs_image_uri`; the workflow sets it for each image. Never put provider API keys here; they live in SSM (`rotate-key.sh`). |

The workflow checks that all four exist and fails with a clear message if one is missing.
This repository is public, so its workflow logs are public too. The workflow masks every e-mail
address found in `TERRAFORM_TFVARS` before Terraform runs. Any other value in that secret may
appear in plan output, so keep only non-sensitive settings in it.

`DEPLOY_ALLOW_DESTROY` is not one of those four, and the deploy does not require it. Leave it
unset on the `production` environment. Only someone who can edit that environment can set it.
Setting it does not by itself deploy anything: set it to `true`, dispatch **Deploy production**
from `main`, then unset it (or set it to `false`) as soon as that run has started. A later
automatic deploy still ignores the variable.

### Who can assume the deploy role

The role's trust policy requires all of the following from the GitHub OIDC token (all `StringEquals`, exact values, no wildcards):

| Claim | Required value |
| --- | --- |
| `aud` | `sts.amazonaws.com` |
| `sub` | `repo:ram290476@48363891/investor-dashboard@1403740156:environment:production` **or** `repo:ram290476/investor-dashboard:environment:production` |
| `repository_id` | `1403740156` |
| `repository_owner_id` | `48363891` |
| `ref` | `refs/heads/main` |
| `job_workflow_ref` | `ram290476/investor-dashboard/.github/workflows/deploy.yml@refs/heads/main` |

- **`sub` format.** GitHub puts immutable owner and repository IDs in the default `sub` for repositories created after 2026-07-15, and for repositories that opt in. This repository was created on 2026-10-04 and uses that format: `gh api repos/ram290476/investor-dashboard/actions/oidc/customization/sub` reports `use_immutable_subject: true` and prefix `repo:ram290476@48363891/investor-dashboard@1403740156`. The older name-only form is also accepted, so a GitHub-side rollback doesn't lock deploys out.
- **Why the ID conditions.** On their own, names can be reused by a different account or repository later. The `repository_id` and `repository_owner_id` conditions ensure that even the name-only `sub` only matches this repository.
- **Where the IDs come from.** They're Terraform variables `github_repository_owner_id` and `github_repository_id`, with defaults of this repository's values. To get them, run `gh api repos/OWNER/REPO --jq '.owner.id, .id'`.
- **Branch.** `sub` alone doesn't restrict the branch: when a job uses an environment, `sub` contains only the repository and environment. The `ref` condition is what AWS enforces for the branch. `workflow_run` runs (after CI on `main`) always run on the default branch, and `workflow_dispatch` runs use the branch they were started from, which must be `main`.
- **Workflow file.** `job_workflow_ref` ties the role to the deploy workflow file as it exists on `main`. For a workflow that isn't reusable, it equals `workflow_ref` and is name-based: GitHub adds the IDs only to `sub`. A token from this repository confirmed this on 2026-10-06.
- **Supported keys.** AWS STS has evaluated GitHub's `ref`, `job_workflow_ref`, `repository_id` and `repository_owner_id` claims since February 2026.

Defense in depth, configured outside AWS:

- the `production` deployment-branch rule (`main` only);
- required reviewers;
- the workflow's own `if:` guard (dispatch from `main`, or a successful CI push to `main`).

If a deploy fails at `configure-aws-credentials` with `Not authorized to perform sts:AssumeRoleWithWebIdentity`, CloudTrail's failed `AssumeRoleWithWebIdentity` event shows the `sub` GitHub sent (in `userIdentity.userName`); compare it with the table above. Changing the trust policy needs an administrator apply, because CI can't modify this role.

#### Jobs image URI and empty-image applies

`module.jobs` creates nothing when `jobs_image_uri` is empty (`enabled_jobs = {}`). A full apply
with an empty URI therefore **destroys** every job Lambda, schedule, trigger and IAM role that
already exists.

The deploy workflow must never pass an empty `jobs_image_uri` once jobs exist:

1. **Bootstrap only** (no ECR repository in state, and no job Lambdas either): one apply with an
   empty URI creates the lake/ECR and the rest of the base stack.
2. **Every later run:** skip that bootstrap apply, build/push a new image, then apply once with
   that image URI. The workflow also refuses to apply if `JOBS_IMAGE_URI` is unset.

The bootstrap check writes `terraform state list` to a file and compares addresses in bash
(`scripts/decide-bootstrap.sh`). Do not pipe that list, or a `printf` of it, into `grep -q`
under `set -o pipefail`. `grep -q` exits at the first match and SIGPIPEs the writer; the
pipeline status is non-zero even though the address is present, and the workflow treats that
as "not in state". Deploy 37496345092 failed that way on `terraform state list | grep -q`.
Deploy 38137774464 (11 Oct 2026, 05:02 PT, commit `f1f5af6`) failed the same way on
`printf | grep -q`: the guard took the empty-image path, Terraform destroyed 201 job
resources (Lambdas, roles, rules, schedules, and log groups), and the second apply recreated
them, which deleted the retained CloudWatch log events.

If `terraform state list` fails, the deploy aborts. An empty list is the only signal for a
first-time bootstrap. A failed list is not an empty state.

Before either apply, `scripts/plan-guard.sh` runs `terraform plan -detailed-exitcode -out=tfplan`
and `scripts/check-plan-destroys.sh` reads `terraform show -json`. The apply uses that saved
plan. The gate aborts when the plan deletes or replaces more than 10 managed resources, or
deletes or replaces any `aws_lambda_function` or `aws_cloudwatch_log_group`. A replacement
counts because it deletes the existing object; replacing a log group drops its events. A plan
that cannot be parsed aborts too. The only waiver is a manual dispatch from `main` while
the `production` environment variable `DEPLOY_ALLOW_DESTROY` is exactly `true`. Set that
variable, dispatch **Deploy production**, then unset it. A `workflow_run` deploy ignores the
variable. The waiver applies only after the plan JSON parses.

#### CloudWatch log groups

These log groups set `lifecycle { prevent_destroy = true }`:

| Resource | What it keeps |
| --- | --- |
| `module.jobs.aws_cloudwatch_log_group.job` | Per-job Lambda logs |
| `module.observability.aws_cloudwatch_log_group.lambda` | Pre-created function log groups |
| `module.api_keys.aws_cloudwatch_log_group.checker` | Key-rotation checker logs |
| `module.user_prefs.aws_cloudwatch_log_group.api_fn` | Preferences API logs |
| `module.user_prefs.aws_cloudwatch_log_group.api_access` | API Gateway access logs |

Terraform rejects the plan before it deletes retained events. That includes the empty-image
failure mode: `module.jobs` drops every job instance when `jobs_image_uri` is empty, and
`prevent_destroy` on the `for_each` log group rejects that plan. Changing retention is an
in-place update and stays allowed. Automatic KMS key-material rotation keeps the same key ARN
and stays allowed. Changing `name`, or the `for_each` key, is a replacement (destroy plus
create), so it is rejected too.

To rename or retire a log group on purpose, knowing that the replacement deletes its events:

1. Remove that resource's `prevent_destroy` block in a reviewed change. On a `for_each` log
   group the block covers every instance, so review the whole plan, not only the one key.
2. On the `production` environment, set the variable `DEPLOY_ALLOW_DESTROY` to `true`.
   Only an admin who can edit that environment can do this.
3. Dispatch **Deploy production** from `main`. The workflow still plans first and records
   the resources it will destroy. A run started by CI on `main` ignores the variable.
4. Unset `DEPLOY_ALLOW_DESTROY` (or set it to `false`) as soon as that dispatch has started.
5. Restore `prevent_destroy` in a follow-up if any of those log groups remain.

`prevent_destroy` is a literal in the configuration. It cannot be turned off from
`terraform.tfvars` or from `DEPLOY_ALLOW_DESTROY`. The variable only lets the destroy gate
accept a plan. Terraform still rejects the plan until the lifecycle block is removed.

#### Admin-only IAM on the deploy role

CI assumes `invdash-terraform-deploy` and is explicitly denied `iam:PutRolePolicy` on that role
(and on the OIDC provider / boundary). So changes to `module.github_deploy` — trust policy,
`iam-for-this-stack` (including the `iam:PassRole` / `iam:PassedToService` allowlist), boundary
attachments — **must be applied by an administrator** before CI can rely on them.

