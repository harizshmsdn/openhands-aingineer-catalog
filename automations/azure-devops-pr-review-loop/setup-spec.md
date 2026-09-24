# Setup spec: what to tell the agent

The human-readable source of truth for both automations. The importable
[`pr-created.automation.json`](./pr-created.automation.json) and
[`pr-review-requested.automation.json`](./pr-review-requested.automation.json)
encode exactly what's below; keep the two in sync when you change a prompt.
This file is also the script to read from if you ever have to create an
automation conversationally instead — see step 3 of the
[README](./README.md).

Both specs assume the `azure-devops` webhook source from README step 1 is
already registered, and that repo scoping is handled by which Azure DevOps
Service Hook subscriptions exist (README step 2), not by anything here. That
means neither prompt hardcodes an org/project/repo — both read it from the
triggering event's payload.

**The first review is automatic; every later one is requested.** Automation 1
fires once, on PR creation. Automation 2 fires only when a human comments
`/review`. Pushes trigger nothing. See the README's "How the loop actually
works" for why this is opt-in rather than push-driven.

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
  >    the skill's convention).
  > 6. End your review comment by telling the developer how the loop
  >    continues: automated review does **not** run on every push. When they
  >    have pushed a round of fixes and want another pass, they should
  >    comment `/review` on this pull request.
  >
  > Only touch the repository and pull request named in this run's event
  > payload. Do not modify code yourself in this conversation — this is a
  > review-only pass; a human pushes any fixes.

## Automation 2 — Review requested

- **Name**: `ADO PR Review Loop - Review Requested`
- **Trigger**: event
  - **source**: `azure-devops`
  - **on**: `ms.vss-code.git-pullrequest-comment-event` — **confirm this
    string.** It's the "Pull request commented on" service hook, and it
    doesn't follow the `git.pullrequest.*` naming of the others. Since the
    webhook source is registered with `event_key_expr: "eventType"`, this
    value has to match whatever ADO actually puts in the payload's
    `eventType` field. Check a real delivery before trusting it.
  - **filter**: `contains(resource.comment.content, '/review')`
- **Prompt**:

  > Someone commented `/review` on an Azure DevOps pull request to request
  > another review pass. Read the triggering event payload for the
  > organization, project, repository, PR id, and the triggering comment's
  > author and content — don't assume any of these, they vary per run.
  >
  > 1. Check who authored the triggering comment. If this agent posted it
  >    rather than a human, stop immediately and do nothing. This agent's own
  >    review comments tell developers to comment `/review` to request the
  >    next pass, so they contain the trigger phrase; acting on one would
  >    make this automation re-trigger itself indefinitely.
  > 2. Fetch the pull request's existing comment threads, including this
  >    agent's previous review comments, and the commits pushed since that
  >    last review.
  > 3. Review the pull request's current diff using the PR-review skill
  >    available in this environment. Follow that skill's instructions for
  >    review depth, findings format, and severity conventions. Give
  >    particular attention to whether the findings from this agent's
  >    previous reviews have actually been addressed by the commits pushed
  >    since.
  > 4. Post the review as a new comment thread on the pull request via the
  >    Azure Repos PR review API, not as a plain top-level comment. State
  >    explicitly which previously-flagged findings are now resolved and
  >    which still stand.
  > 5. If the review has no blocking findings, mark it as approved (or per
  >    the skill's convention).
  > 6. End your review comment by telling the developer that automated
  >    review does not run on pushes — when they have pushed the next round
  >    of fixes and want another pass, they should comment `/review` again.
  >
  > Only touch the repository and pull request named in this run's event
  > payload. Do not modify code yourself in this conversation — this is a
  > review-only pass; a human pushes any fixes.

### The self-trigger hazard, and why step 1 exists

The filter is a plain substring match on comment content, and the agent's own
closing comment deliberately contains `/review` so developers can discover the
command. That combination is a self-trigger loop waiting to happen: the bot
posts a review mentioning `/review`, the comment event fires, the filter
matches, the bot reviews again, forever.

Step 1's author check is the real guard. Keep it first, and keep it
unconditional. Once you know the agent's ADO identity string, tighten the
filter to exclude it too — something like
`contains(resource.comment.content, '/review') && resource.comment.author.uniqueName != '<agent-identity>'`
— so the platform drops those events before a conversation ever starts. Until
then you're paying one conversation per self-comment to have the agent notice
and bail.

## The PR-review plugin, in both automations

Neither prompt assumes the PR-review skill is loaded by default — both JSON
files make these plugin-backed automations, pinning this catalog's own
`pr-review` plugin:

```json
"plugins": [
  {
    "repository": "https://github.com/harizshmsdn/openhands-aingineer-catalog.git",
    "ref": "v0.1.5",
    "path": "plugins/pr-review"
  }
]
```

That `PluginSource` shape is inferred, not confirmed — it's the analogue of
this catalog's own `CATALOG_REF` pinning, and it's the field most likely to
need correcting on first import. See the README's open-questions section.
