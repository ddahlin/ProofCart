# `QA_AGENT_READ_PAT` — creation steps

The `defect-scorecard` workflow checks out the **private** QA-agent generator
(`ddahlin/QAAITESTArtifact`). This repo's ephemeral `GITHUB_TOKEN` cannot read another
private repository, so that checkout needs a token. This file records exactly how it is
scoped and why — least privilege now, deliberately.

## 1. Mint the token

<https://github.com/settings/personal-access-tokens/new> (Fine-grained, **not** classic)

| Field | Value |
|---|---|
| **Token name** | `QA_AGENT_READ_PAT` (or `shopcheck-ci-reads-qa-agent`) |
| **Resource owner** | `ddahlin` |
| **Expiration** | 90 days (calendar a renewal — an expired token fails the checkout, which reads as a red scorecard job) |
| **Repository access** | **Only select repositories** → `ddahlin/QAAITESTArtifact` |
| **Permissions** → Repository permissions | **Contents: Read-only** — and nothing else |

Leave every other permission at *No access*. In particular do **not** grant Actions,
Metadata-write, or organization permissions. (GitHub adds `Metadata: Read-only`
automatically; that is expected and unavoidable.)

## 2. Store it as a secret in **this** repo

<https://github.com/ddahlin/ProofCart/settings/secrets/actions/new>

| Field | Value |
|---|---|
| **Name** | `QA_AGENT_READ_PAT` |
| **Secret** | the token value |

A **repository** secret is correct here, not an environment secret: the checkout step
runs before anything environment-scoped matters, and the job already claims `beta` for
the `SHOPCHECK_*` seed credentials.

Or from the CLI:

```bash
gh secret set QA_AGENT_READ_PAT --repo ddahlin/ProofCart
```

## 3. Verify

```bash
gh workflow run defect-scorecard.yml --repo ddahlin/ProofCart
gh run watch --repo ddahlin/ProofCart
```

A green run ends with a job-summary table showing **4 caught / 0 not-covered / 0 missed**
with D1→TC-201, D2→TC-080, D3→TC-202, D4→TC-153+TC-155, plus an honest not-run annotation
for the two artifact-bearing expectation checks (the enriched artifact is gitignored and
absent in CI).

## Why read-only, when the follow-on needs more

The recorded next step (QA-agent repo `BACKLOG.md` → Phase 3.5) is a
`repository_dispatch` triage loop, which needs **`contents: write`** on the same repo.
Upgrading or reissuing this token at that point is the plan — a deliberate step taken
when that loop is actually built, with eyes open. One token serving two purposes is a
decision to make then, not a scope granted early "just in case".
