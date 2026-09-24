# Azure DevOps PR Review Loop

An OpenHands event-based automation that reviews every pull request in a
chosen Azure DevOps project once on creation, then re-reviews it whenever a
developer asks for another pass by commenting `/review`.

Re-review is **requested, not automatic**. Pushing commits triggers nothing.
See [How the loop actually works](#how-the-loop-actually-works).

This is **not** a catalog plugin. Plugins in `plugins/` are skills the agent
loads *during* a conversation; what's described here is an OpenHands
Automation — config that controls *when a conversation starts in the first
place*. It doesn't need a `plugin.json` or a marketplace entry.

## How this repo's files work now

This directory holds two importable files —
[`pr-created.automation.json`](./pr-created.automation.json) and
[`pr-review-requested.automation.json`](./pr-review-requested.automation.json)
— plus
[`setup-spec.md`](./setup-spec.md), which is the human-readable source of
truth for the same trigger + prompt pairs.

The JSON is deliberately **half a deployment mechanism, not a whole one**.
Import carries the expensive part (prompt, plugin pinning, timeout, and a
written record of which event each automation is meant to listen for), and
lands inert: created disabled, with its event source swapped for the
`agent-canvas-import` placeholder. A human operator then finishes the job in
the UI by binding the real, tenant-scoped `azure-devops` connection — the
step that import structurally cannot do, because it's the step that involves
a credential. See [Setup](#setup) step 3.

So the `trigger.source` / `trigger.on` values in these files are **intent,
not live config**. They tell the operator (and the next reader) what to
re-arm to; they do not survive import.

## What's actually confirmed, vs. still open

Verified directly against
[OpenHands/extensions](https://github.com/OpenHands/extensions/tree/main/automations)
(`index.d.ts`, `interface.json`, `catalog.schema.json`, and the
`github-pr-reviewer` / `custom-automation` catalog manifests) — not just prose
docs:

- **Import cannot originate a live event trigger.** `interface.json` sets
  `importDefaults.placeholderEventSource: "agent-canvas-import"`, and
  `index.d.ts` says outright this exists to "keep an import inert." Every
  imported automation's real trigger is swapped for a placeholder. This is
  also why OpenHands' own "Exported file format" doc only shows a
  **schedule**-trigger example: schedule is the one trigger kind whose real
  config actually survives export/import. This is a limit on what import
  *originates*, not a reason to avoid import — hence the re-arm step below.
- **The file envelope is confirmed**: `{ "version": 1, "kind":
  "automation", "spec": { … } }`, from the "Exported file format" section of
  the [managing-automations
  doc](https://docs.openhands.dev/openhands/usage/agent-canvas/managing-automations).
  The doc's own example shows `name`, `trigger`, `enabled`, `prompt`,
  `repository`, and `model` inside `spec`, and states in prose that `spec`
  also carries `plugins` and notification settings — without showing their
  shape. Imports are always created disabled regardless of `enabled`.
- **What you can edit on an existing automation is capped.** `index.d.ts`'s
  `AutomationAttributeName` is `name | prompt | model | timeout | schedule`
  only — no trigger, no filter, no repository. So even post-creation, there's
  no documented way to just "edit the filter" to retarget an existing
  automation at a different repo.
- **The trigger shape is confirmed**: `source` / `on` (event type) / `filter`
  (JMESPath), taken verbatim from `custom-automation/manifest.json`'s
  `setup.form.triggers.event`. `event-source` reads from whatever you've
  registered via the webhooks API, which is why the Phase 1 webhook
  registration below is still the right first step — it's what makes
  `azure-devops` a selectable source at all.
- **Azure DevOps is not a `repo-picker` provider.** `catalog.schema.json`
  hard-codes `"provider": { "enum": ["github", "gitlab", "bitbucket"] }`. The
  convenience "pick a repo, we clone it for you" field genuinely doesn't
  support ADO in this schema.
- **Still open / unverified:** whether that last point means the agent has
  *no* built-in ADO repo access (and the prompt must instruct it to clone via
  a PAT secret), or whether repo access instead comes from a separate,
  org-level Azure DevOps integration (Entra ID sign-in, browsing Azure Repos)
  that OpenHands' own marketing describes, independent of this repo-picker
  widget. This repo's schema snapshot doesn't settle it either way — confirm
  in your actual deployment before assuming either.
- **Still open / unverified:** whether the `plugins` field (for a
  plugin-backed automation) takes a bare plugin name, or a structured
  `PluginSource` (repository + ref + path) analogous to this catalog's own
  `CATALOG_REF` pinning. `index.d.ts` only says it's "a PluginSource list,
  usually `{{form.plugins}}`", each source possibly including "an optional
  ref and repository path" — consistent with pointing at
  `{repository: <this catalog's URL>, ref: <tag>, path: "plugins/<pr-review-plugin>"}`,
  but not confirmed. **Both JSON files here commit to that shape** — it's the
  single most likely thing to need correcting on first import. If the
  importer rejects it, try a bare plugin name string in the array instead,
  and fix the files to match what actually took.
- **`spec.repository` is deliberately absent from both files.** It's a
  GitHub-provider-only field (see the `repo-picker` point above), so there's
  nothing valid to put in it for an Azure Repos PR. Repo access has to come
  from the ADO side — see the unresolved question above about whether that's
  a PAT secret the prompt uses, or an org-level ADO integration.

## Because per-automation repo retargeting isn't confirmed editable, put repo selection in Azure DevOps instead

Since there's no confirmed way to edit an existing automation's filter or
repo after creation, don't hardcode a single repo into the OpenHands side at
all. Instead:

- Keep the OpenHands automation's filter generic (matches PR created/updated
  events from the `azure-devops` source, no repo-name restriction), and have
  its prompt read the org/project/repo/PR id straight out of the triggering
  event's payload (`resource.repository.*`, `resource.pullRequestId`, etc.)
  rather than assuming a fixed one.
- Do repo selection on the **Azure DevOps side**: each Service Hook
  subscription (below) is already scoped to a specific repository via its own
  filter in the ADO UI. Adding, removing, or swapping which repos this
  applies to is then just editing/adding ADO service hook subscriptions —
  native, well-documented, and doesn't depend on any of the still-open
  questions above about editing an OpenHands automation post-creation.

This is the "modifiable to apply to any repo we select" requirement, just
satisfied on the ADO side instead of the OpenHands side, since that's the
side we can actually confirm is editable.

## How the loop actually works

There is no "loop" or "stop condition" primitive in OpenHands automations.
`AutomationTriggerKind` is `cron | event` — that's the whole vocabulary. An
automation says "when X happens, start a conversation with this prompt," and
nothing more: each firing spawns a fresh, independent conversation that
inherits no state from the one before it. There is no iteration count, no
termination-condition evaluator, no wait primitive, and no cancellation.

So the loop is externalized into Azure DevOps. ADO holds the durable state
(the PR, its commits, its comment threads), ADO emits events on change, and
each event independently triggers a stateless review pass. The PR *is* the
state machine; the agent is a pure function of `(PR state at time T)`:

1. **PR created** → agent reviews once, automatically.
2. Developer pushes fixes — **nothing happens.** Pushes are not a trigger.
3. Developer comments `/review` → agent re-reviews, and reports which of its
   previous findings are now resolved.
4. Repeat 2–3 until the agent approves, or until the developer stops asking.

### Why re-review is requested rather than push-driven

An earlier version of this fired on `git.pullrequest.updated`, re-reviewing on
every push. That's the obvious design and it's a trap: developers push WIP
commits, typo fixes, rebases and target-branch merges, so most pushes produce
a full review of half-finished work. Comments accumulate against stale diffs
and people learn to tune the bot out.

The platform's own flagship reviewer reaches the same conclusion —
`github-pr-reviewer` gates on `triggerLabel` ("Only pull requests carrying
this label are reviewed") and `triggerReviewer` ("GitHub login whose review
request starts an event-driven review"). It is opt-in, not push-driven.

Requesting by **comment** also beats the alternative of marking the final
commit message, for a mechanical reason: the JMESPath `filter` is evaluated
against the event payload *before* a conversation starts. A comment event's
payload contains the comment text, so `contains(resource.comment.content,
'/review')` gates everything at the platform level and pushes cost nothing.
The `git.pullrequest.updated` payload carries `lastMergeSourceCommit` as an id
and URL but not the commit *message*, so a `[review]`-style marker couldn't be
filtered on — every push would still spin up a conversation just to read a
string and bail.

### Where `/stop-review` went

It's gone from the re-review path, because opt-in makes it redundant: if
reviews only happen when asked, not asking *is* the stop. The check survives
in `pr-created.automation.json` only, and even there it's close to vestigial —
the PR-created webhook fires before any human could realistically comment. Say
the word if you'd rather drop it there too and reclaim the tokens.

To change the `/review` phrase, edit it in both `.automation.json` files, in
`setup-spec.md`, in the live automations' prompts (one of the five editable
attributes, so the UI won't drift back on its own), **and** in the
`pr-review-requested` trigger's filter — which is *not* editable post-creation,
so a phrase change may mean recreating that automation.

## Setup

### 0. Prerequisite: the `pr-review` plugin must exist at the pinned tag

Both JSON files pin
`plugins/pr-review` in this catalog at ref **`v0.1.5`**. That plugin (its
`.plugin/plugin.json`, its `skills/pr-review/SKILL.md`, and its
`marketplace.json` entry) has to be merged and that tag pushed before either
automation can resolve its plugin source at run time. If you tag a different
version, update the `ref` in both files to match — nothing else discovers it
for you.

### 1. Register the Azure DevOps webhook source (once, org-wide)

```bash
curl -X POST "https://<your-openhands-enterprise-host>/api/automation/v1/webhooks" \
  -H "Authorization: Bearer ${OPENHANDS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Azure DevOps",
    "source": "azure-devops",
    "event_key_expr": "eventType",
    "signature_header": "Authorization"
  }'
```

Save the returned `webhook_url` — it's reused by every ADO repo/project you
ever point at this, not just the ones below. This step is what registers
`azure-devops` as a source at all — which is precisely why step 3b can offer
it to you to re-arm with. Import never creates a source; it only ever selects
one that already exists.

Azure DevOps service hooks don't do HMAC request signing like GitHub/Linear;
they only offer Basic Auth on the outgoing webhook. `signature_header:
"Authorization"` is a best guess at how to verify that — confirm it actually
gets checked before treating it as a real security boundary.

### 2. Create Azure DevOps Service Hook subscriptions, one per repo

For **each** repository you want covered, in that project: **Project
Settings → Service Hooks → Create subscription → Web Hooks**, twice:

- Trigger: **Pull request created**, filtered to this repository
- Trigger: **Pull request commented on**, filtered to this repository

Both point at the same `webhook_url` from step 1. Note the second one is *not*
"Pull request updated" — pushes deliberately trigger nothing here.

While you're in this UI, grab the exact event type string ADO sends for the
comment trigger and check it against the `on` value in
`pr-review-requested.automation.json` (currently
`ms.vss-code.git-pullrequest-comment-event`). That one doesn't follow the
`git.pullrequest.*` naming the others use, and since step 1 registered the
source with `event_key_expr: "eventType"`, it has to match whatever ADO
actually puts in the payload's `eventType` field. Easiest confirmation is to
comment on a test PR and look at the delivery ADO records.

### 3. Import both JSON files, then re-arm each trigger in the UI

**3a. Import.** Automate view → **Import automation** → pick
[`pr-created.automation.json`](./pr-created.automation.json). Repeat for
[`pr-review-requested.automation.json`](./pr-review-requested.automation.json).
Each lands disabled, with prompt, plugin pin, and timeout intact, and with its
event source replaced by the `agent-canvas-import` placeholder.

**3b. Re-arm.** Open each imported automation and bind the live trigger:

| Automation | Event source | Event type | Filter |
| --- | --- | --- | --- |
| `ADO PR Review Loop - PR Created` | `azure-devops` | `git.pullrequest.created` | _(none)_ |
| `ADO PR Review Loop - Review Requested` | `azure-devops` | `ms.vss-code.git-pullrequest-comment-event` | `contains(resource.comment.content, '/review')` |

The `azure-devops` source is only selectable here because of step 1 — that's
what the webhook registration buys you.

The empty filter on PR-created is deliberate: repo scoping lives in the ADO
service hook subscriptions from step 2, for the reasons above. The filter on
Review Requested is doing a different job — it's what stops every ordinary PR
comment from starting a conversation.

> **This is the step to watch.** It assumes the post-import configuration
> flow lets you set a trigger, which is *not* the same surface as the
> `name | prompt | model | timeout | schedule` edit form documented in
> `index.d.ts` — and that list conspicuously has no trigger in it. If the
> imported automation offers no way to bind a source and event type, then on
> this deployment import is a prompt-and-plugin carrier only, and the
> conversational path below is the real creation mechanism. Record which one
> it turned out to be, here, the first time you run this.

**3c. Enable** each one, and confirm the trigger the UI now shows matches the
`trigger` block in the corresponding JSON file. If they disagree, the UI is
right and the file is stale.

If import rejects a file outright, fall back to describing each automation
conversationally ("New Automation" / the `openhands-automation` skill) using
[`setup-spec.md`](./setup-spec.md) as the script — then fix the JSON here to
match whatever the creation flow actually accepted.

### 4. Keep the JSON in sync after any UI change

These files are now the versioned source of truth for the prompt text, so
changing a prompt means editing the file here **and** applying the same edit
in the UI (`prompt` is one of the five editable attributes — name, prompt,
model, timeout, schedule). Exporting a live automation and diffing it against
the file here is the cheap way to catch drift. (Whether a live event
automation's export retains its real trigger fields, or redacts them the way
import does, is still unconfirmed — check the first time you export one, and
record the answer in this README.)
