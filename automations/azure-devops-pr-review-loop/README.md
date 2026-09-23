# Azure DevOps PR Review Loop

An OpenHands event-based automation that reviews every pull request in a
chosen Azure DevOps project, re-reviews it each time new commits are pushed,
and stops reviewing a given PR the moment a human comments `/stop-review` on
it.

This is **not** a catalog plugin. Plugins in `plugins/` are skills the agent
loads *during* a conversation; what's described here is an OpenHands
Automation — config that controls *when a conversation starts in the first
place*. It doesn't need a `plugin.json` or a marketplace entry.

## How this repo's files work now

There is **no importable JSON file in this directory**, on purpose. Earlier
drafts here assumed you could hand-author an `.automation.json` with a live
event trigger and import it. That's wrong — see below — so instead
[`setup-spec.md`](./setup-spec.md) holds the two automation specs (trigger +
prompt) as plain reference text: what to tell the agent when creating these
conversationally, and what to diff a real export against afterward.

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
  config actually survives export/import.
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
  but not confirmed.

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

There is no "loop" or "stop condition" primitive in OpenHands automations —
each trigger fires a fresh, independent conversation. The loop is an emergent
property of two automations plus PR state used as memory:

1. **PR created** → agent reviews once.
2. Developer pushes fixes → **PR updated** fires → agent re-reviews. This
   repeats for every push, which is the "loop".
3. **Stopping it**: there's no platform-level "cancel automation" triggered by
   a comment. Instead, both prompts (in `setup-spec.md`) instruct the agent to
   read the PR's comment threads *before* reviewing, and skip the review
   entirely if it finds a human comment saying `/stop-review` posted after
   the agent's own last review. Change that phrase in both prompts if you
   want something else.

## Setup

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
ever point at this, not just the ones below. This step is unaffected by
everything above: it's what registers `azure-devops` as a source at all, and
is separate from the (broken) idea of importing a finished automation.

Azure DevOps service hooks don't do HMAC request signing like GitHub/Linear;
they only offer Basic Auth on the outgoing webhook. `signature_header:
"Authorization"` is a best guess at how to verify that — confirm it actually
gets checked before treating it as a real security boundary.

### 2. Create Azure DevOps Service Hook subscriptions, one per repo

For **each** repository you want covered, in that project: **Project
Settings → Service Hooks → Create subscription → Web Hooks**, twice:

- Trigger: **Pull request created**, filtered to this repository
- Trigger: **Pull request updated**, filtered to this repository

Both point at the same `webhook_url` from step 1.

### 3. Create the two automations conversationally — not by importing JSON

Open the Automations UI ("New Automation" / the `openhands-automation`
skill) and describe each one, using the trigger and prompt text in
[`setup-spec.md`](./setup-spec.md) verbatim as what you tell the agent. Two
automations: one triggered on `git.pullrequest.created`, one on
`git.pullrequest.updated`. This is the only path confirmed to actually wire a
live trigger.

### 4. Export afterward, for version control only

Once live, export each automation and save the result here (e.g.
`pr-created.automation.json`) so this directory has a real, versioned
snapshot to diff against next time you change the prompt. Don't re-import
these to deploy elsewhere — treat them as documentation of what's live, not
as a deployment mechanism. (Whether a live event automation's export retains
its real trigger fields, or also redacts them the way import does, is itself
unconfirmed — check once you have one to export.)
