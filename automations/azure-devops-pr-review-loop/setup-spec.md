# Setup spec: what to tell the agent

Reference text for step 3 of the [README](./README.md) — describe these to
the agent when creating each automation conversationally. **Not** an
importable file; see the README for why.

Both specs assume the `azure-devops` webhook source from README step 1 is
already registered, and that repo scoping is handled by which Azure DevOps
Service Hook subscriptions exist (README step 2), not by anything here. That
means neither prompt hardcodes an org/project/repo — both read it from the
triggering event's payload.

## Automation 1 — PR created

- **Name**: `ADO PR Review Loop - PR Created`
- **Trigger**: event
  - **source**: `azure-devops`
  - **on**: `git.pullrequest.created`
  - **filter**: _(none — repo scoping happens via which ADO service hook
    subscriptions exist)_
- **Prompt**:

  > A pull request was just created in Azure DevOps. Read the triggering
  > event payload for the organization, project, repository, PR id, title,
  > author, and source/target branch — don't assume any of these, they vary
  > per run.
  >
  > 1. Fetch the pull request's existing comment threads.
  > 2. If any thread contains a comment from a human reviewer (not from this
  >    agent) with the exact text `/stop-review` posted after this agent's
  >    most recent review comment, stop here and do not review — a developer
  >    has opted this PR out of automated review.
  > 3. Otherwise, review the pull request's current diff using the PR-review
  >    skill available in this environment. Follow that skill's instructions
  >    for review depth, findings format, and severity conventions.
  > 4. Post the review as comment thread(s) on the pull request via the
  >    Azure Repos PR review API, not as a plain top-level comment.
  > 5. If the review has no blocking findings, mark it as approved (or per
  >    the skill's convention) and note that automated review will run again
  >    only if new commits are pushed, and can be skipped by commenting
  >    `/stop-review`.
  >
  > Only touch the repository and pull request named in this run's event
  > payload. Do not modify code yourself in this conversation — this is a
  > review-only pass; a human pushes any fixes.

## Automation 2 — PR updated

- **Name**: `ADO PR Review Loop - PR Updated`
- **Trigger**: event
  - **source**: `azure-devops`
  - **on**: `git.pullrequest.updated`
  - **filter**: _(none, same reasoning as above)_
- **Prompt**:

  > A pull request in Azure DevOps was just updated (this fires on new
  > pushes, but also on status/reviewer-vote changes). Read the triggering
  > event payload for the organization, project, repository, PR id, and what
  > changed — don't assume any of these, they vary per run.
  >
  > 1. If this update was not caused by new commits on the source branch
  >    (e.g. it was just a reviewer vote or status change), stop here and do
  >    not review again.
  > 2. Fetch the pull request's existing comment threads.
  > 3. If any thread contains a comment from a human reviewer (not from this
  >    agent) with the exact text `/stop-review` posted after this agent's
  >    most recent review comment, stop here and do not review — a developer
  >    has opted this PR out of further automated review, even though new
  >    commits were pushed.
  > 4. Otherwise, review the pull request's current diff (the new commits,
  >    and whether prior findings were addressed) using the PR-review skill
  >    available in this environment. Follow that skill's instructions for
  >    review depth, findings format, and severity conventions.
  > 5. Post the review as a new comment thread on the pull request via the
  >    Azure Repos PR review API, not as a plain top-level comment.
  >    Reference whether previously-flagged issues were resolved.
  > 6. If the review has no blocking findings, mark it as approved (or per
  >    the skill's convention) and note that automated review will run again
  >    only if further commits are pushed, and can be skipped by commenting
  >    `/stop-review`.
  >
  > Only touch the repository and pull request named in this run's event
  > payload. Do not modify code yourself in this conversation — this is a
  > review-only pass; a human pushes any fixes.

## If the automation needs the PR-review plugin loaded explicitly

If the agent doesn't already have the PR-review skill loaded by default and
this needs to be a plugin-backed automation instead of a plain prompt one,
the `plugins` field's exact shape is one of the unconfirmed items in the
README. The best-supported guess, by analogy to this catalog's own
`CATALOG_REF` pinning, is a `PluginSource`-shaped entry along the lines of:

```json
{
  "repository": "<this catalog's git URL>",
  "ref": "<the tag your agents are pinned to>",
  "path": "plugins/<pr-review-plugin-name>"
}
```

Validate this against whatever the conversational setup flow actually
accepts when you get there — don't take the shape above as confirmed.
