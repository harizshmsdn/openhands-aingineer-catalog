---
name: pr-review
description: "Summarize and review all changes on the current branch and assess whether they break existing functionality. Use when the user says things like `review this branch`, `summarize the changes on this branch`, `review my PR before I open it`, `does this branch break anything`, `review the diff vs main`."
version: "1.0"
metadata:
  author: Ken
triggers:
  - review this branch
  - summarize the changes on this branch
  - review my PR before I open it
  - does this branch break existing functionality
  - review the diff vs main
---

# PR Review

Produce a thorough, PR-ready review of the current branch: what changed, whether it's safe to ship, and what risks remain.

> **Started by an Azure DevOps PR automation?** Read
> [Running as an ADO PR automation](#running-as-an-ado-pr-automation) at the
> bottom first. The review *methodology* in this document is unchanged there,
> but where the diff comes from, where findings go, and how line references
> are expressed are all different. That section says which steps below still
> apply verbatim and which it overrides.

## When to use

Trigger phrases:
- "review this branch"
- "summarize the changes on this branch"
- "review my PR before I open it"
- "does this branch break existing functionality"
- "review the diff vs main"

Distinct from a code-review of a single file or hunk — this is a **whole-branch** review. Distinct from the built-in bare `/review` skill, which only dumps the diff and asks for comments. This one runs the process end-to-end.

## Goal

By the end, the user should have:
1. A clean list of what genuinely changed on **this** branch (not counting commits already merged to main).
2. A tree view of the changed files, so the shape of the change is visible at a glance.
3. A per-area explanation of the behavioural change.
4. A judgement on regression risk with reasoning per failure path.
5. Verification signals (typecheck, tests) with pre-existing failures separated from new ones.
6. Explicit line-anchored references so the user can jump to the code.

## Steps

### 1. Isolate the branch's actual work

Merge commits from `main` can bloat `git log main..HEAD` and hide the real changes. Fetch first, then diff against `origin/main`:

```bash
git fetch origin main
git log origin/main..HEAD --oneline
git diff origin/main...HEAD --stat
```

The three-dot `...HEAD` diff is what actually landed on this branch relative to their common ancestor. Two-dot `..HEAD` shows commits reachable from HEAD but not `origin/main` — useful for the log listing but not the diff.

If `git log main..HEAD` shows commits like `Merged PR NNNN:` at the top, those are back-merges from main and are NOT this branch's work. Confirm by comparing counts:

```bash
git log main..HEAD --oneline | wc -l          # inflated by back-merges
git log origin/main..HEAD --oneline | wc -l   # actual branch commits
```

**Report the real count to the user.** If the branch's true work is 2 commits out of 11 shown by naive `git log`, say so.

### 2. Read the diff — but scope it

Get the file list from `--stat`. For each file, view the diff:

```bash
git diff origin/main...HEAD -- <file>
```

Do NOT read the whole `git diff origin/main...HEAD` in one shot if the branch is large — it burns context. Diff file-by-file so you can reason about each area.

If a file's diff includes hunks that look like pure reordering (same lines, different position), state that explicitly. Reordering with no logic change has a very different risk profile from behavioural change.

### 3. Understand the behavioural intent

For each meaningful change, answer:
- **What was the code doing before?** (read the pre-change side of the diff, and if needed `git show origin/main:<path>` for full context)
- **What is it doing now?**
- **Why did the change happen?** (commit message + the observable effect)

If the commit messages are terse (`chore: update type`), don't rely on them — read the code and describe the effect yourself.

### 4. Walk the failure paths — this is the core of "does it break things"

For any behavioural change, the review must cover:

- **Happy path** — does it do the intended new thing?
- **Failure paths** — when the new step fails (network error, `Promise.allSettled` rejection, missing data), does the code fall back to the previous behaviour or does it corrupt state?
- **Opt-out path** — if a user didn't opt into the new feature (e.g. "also add to directory" not checked), is behaviour identical to before?
- **Payload shape** — did the wire contract to any downstream API change? If not, existing consumers are safe.
- **State restructuring** — if `if/else` became `if / else if`, walk each branch and confirm the toast/side-effect fires in the same cases as before (or explain the intentional difference).

The template to emit for the user:

```
1. <path> succeeds → <new correct behaviour>.
2. <path> fails → falls back to <old behaviour>. Identical to previous.
3. <opt-out> → map/flag stays empty → identical to previous.
4. Payload to <endpoint> unchanged except <field> now sometimes populated.
```

That structure makes the "no regression" claim auditable.

### 5. Verify with the project's own signals

Run whatever the project uses. In a Next.js/TS project that's usually:

```bash
npm run typecheck 2>&1 | tail -30
```

**Filter to the branch's files.** A large repo will have pre-existing errors in scratch/legacy dirs. Filter with grep to show only errors in the files this branch touched:

```bash
npm run typecheck 2>&1 | grep -E "(<changed-file-1>|<changed-file-2>)" | head -30
```

If a project has known pre-existing failures (e.g. `temp/` in mesyuarat), acknowledge them and note they are unrelated.

For tests:

```bash
npx vitest run 2>&1 | tail -25          # summary
npx vitest run 2>&1 | grep -E "^\s*(❯|×|FAIL|●)"  # find failed test names
```

If a test fails, **check whether the failing test file was actually modified on this branch**:

```bash
git diff origin/main...HEAD -- <failing-test-file>
```

If the diff is empty, the failure is pre-existing on main and NOT caused by this branch. Say so explicitly. Do not run destructive stash/checkout gymnastics to "confirm" it — the empty diff is proof enough. If the user has denied destructive git ops, respect that.

### 6. Note minor issues without blocking

If you find small inconsistencies (e.g. one call site still uses the raw API while others use a new helper), flag them as **non-blocking** cleanup. Distinguish clearly between "this is a bug" and "this could be tidier". Reviews that don't distinguish severity get ignored.

### 7. Structure the report

Emit exactly these sections, in order:

```
## Branch review: <branch-name>

### Scope
- N commits unique to branch (list them). Note if the naive log count was inflated by back-merges.

### What changed
- File count, line count.
- Tree view of changed files (see "Tree view of changed files" convention below).
- 1–2 paragraphs: what was the *behavioural* change. Frame as "Before / After".
- Bulleted list of call sites with file:line links.
- Any supporting changes (type updates, helper introductions).

### Regression risk — assessment
- Verdict word ("Low", "Medium", "High") in bold.
- The numbered failure-path walk from step 4.

### Verification
- Typecheck: clean / N errors (branch files only).
- Tests: X/Y pass. If a failure exists, identify it and confirm whether it's pre-existing on main.

### Minor observations (not blocking)
- Bullet each. Distinguish from bugs.

### Verdict
- One sentence: safe to ship / needs fixes / needs discussion.
```

## Conventions

- **Line references use markdown links** in the VS Code extension format: `[filename.tsx:123](src/path/to/filename.tsx#L123)` or ranges `[filename.tsx:100-120](src/path/to/filename.tsx#L100-L120)`. Never bare backticks.
- **Be specific.** "There's a potential issue with X" is useless. "If `createContactInDirectory` rejects, `map.get(email)` returns `undefined` and the attendee falls back to `c.id || null` — same as pre-branch behaviour" is a review.
- **Do not fabricate risks.** If every failure path is preserved, say the risk is low and explain why. False-flagging problems for the sake of looking thorough wastes the reviewer's time.
- **Do not modify code** during a review unless the user explicitly asks. Reviewing is read-only.

## Tree view of changed files

Always emit this as part of "What changed". Source paths from `git diff origin/main...HEAD --name-only`.

- Group by common parent directories, collapsing single-child chains (e.g. `src/app/api/meetings/[id]/` on one line rather than four levels of nesting).
- Use box-drawing characters: `├──`, `└──`, `│`.
- Annotate new files with `(new)` on the right. Deleted files with `(deleted)`. Renamed files with `(renamed from <old>)`. Modified files get no annotation.
- End with a one-line count: `N files: X new, Y modified` (and deleted/renamed if any).
- No file:line links in this view — it's a locator, not a review. The review itself already carries the links.
- If the user later asks for a filtered view (e.g. "without the test folder"), re-emit the tree with `__tests__/` and `*.test.*` paths excluded.

Example shape:

```
src/
├── api-client/
│   └── index.ts
├── components/meeting/
│   ├── BotRescheduleConfirmModal.tsx   (new)
│   └── MeetingDetailsForm.tsx
└── lib/
    └── botReschedule.ts                (new)
```

## Do NOT

- Do not run `git diff main..HEAD` naively without checking `origin/main` — you'll misattribute merged commits to this branch.
- Do not read the entire branch diff in one Bash call for a large branch — diff per-file.
- Do not run destructive git operations (`stash`, `checkout HEAD --`, `reset`) to "verify" a claim about main. The `git diff origin/main...HEAD -- <file>` empty result is authoritative.
- Do not report a test failure as a branch regression without first checking whether the failing file was touched on the branch.
- Do not conflate "cosmetic cleanup opportunity" with "bug". Reviews lose credibility when everything is flagged at the same severity.
- Do not write commits, push, or open the PR as part of the review. Wait for the user to explicitly ask.

---

# Running as an ADO PR automation

Everything above assumes an interactive review of a locally checked-out
branch, reported back in chat. When this skill is loaded by the automations in
`automations/azure-devops-pr-review-loop/`, the analysis is identical but the
plumbing is not: there may be no local clone, the target branch is rarely
`main`, and the review is published to the pull request rather than written to
a chat transcript.

All endpoints below are rooted at:

```
https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repositoryId}
```

with `organization`, `project`, `repositoryId` and `pullRequestId` taken from
the triggering event payload (`resource.repository.*`, `resource.pullRequestId`).
Never hardcode them. `api-version=7.1` throughout; on older Azure DevOps Server
installs some of these need `7.1-preview.1`.

## Step A — Establish your own identity, first, every run

```bash
GET https://dev.azure.com/{organization}/_apis/connectionData?api-version=7.1
```

`authenticatedUser.id` is your identity GUID. One call, two uses: it's the
`reviewerId` you need to cast a vote, and it's how you tell your own past
comments apart from a human's. Do this before anything else — the
review-requested automation's first instruction is to bail if *you* authored
the triggering comment, and that check needs this value.

## Step B — Get the diff

**If a clone is available**, work as the methodology above describes, but
diff against the PR's real target, not `main`:

```bash
git fetch origin "{targetRefName}" "{sourceRefName}"
git diff "origin/{targetBranch}...origin/{sourceBranch}" --stat
```

`targetRefName` and `sourceRefName` arrive as full refs
(`refs/heads/develop`); strip the `refs/heads/` prefix. The three-dot form
still matters for the same reason it does above.

Cloning with a PAT:

```bash
git clone "https://anything:${ADO_PAT}@dev.azure.com/{org}/{project}/_git/{repo}"
```

**If no clone is available**, use PR iterations instead — each push to the
source branch creates one, which makes them the natural unit for "what changed
since last time":

```bash
GET .../pullRequests/{pullRequestId}/iterations?api-version=7.1
GET .../pullRequests/{pullRequestId}/iterations/{id}/changes?api-version=7.1
```

| Situation | Call |
| --- | --- |
| First review | changes for the latest iteration |
| Re-review | `.../iterations/{latest}/changes?$compareTo={iterationAtLastReview}` |

Fetch file contents at a specific commit with:

```bash
GET .../items?path={path}&versionDescriptor.version={commitId}&versionDescriptor.versionType=commit&includeContent=true&api-version=7.1
```

Iteration-based diffing is strictly better than reconstructing commit ranges by
hand for the re-review case — it answers "what did they change since I last
looked" directly.

## Step C — Which steps above still apply

| Step above | In automation |
| --- | --- |
| 1. Isolate the branch's actual work | **Replaced** by Step B. Iterations are the equivalent of filtering out back-merges. |
| 2. Read the diff, but scope it | **Applies verbatim.** File-by-file, never the whole diff at once. |
| 3. Understand the behavioural intent | **Applies verbatim.** |
| 4. Walk the failure paths | **Applies verbatim** — this is the core of the review and the main thing worth the tokens. |
| 5. Verify with the project's own signals | **Only if a clone exists.** With API-only access you cannot run typecheck or tests. Say so explicitly in the summary rather than silently omitting the Verification section. |
| 6. Note minor issues without blocking | **Applies verbatim**, and now load-bearing — see Step E. |
| 7. Structure the report | **Replaced** by Step D. |

## Step D — Publish the review as threads

Post **one summary thread** plus **one anchored thread per specific finding**.
Do not dump the whole review into a single comment: anchored threads let a
developer resolve findings individually, which is what makes the loop
converge.

Summary thread — omit `threadContext` entirely so it lands at PR level:

```json
POST .../pullRequests/{pullRequestId}/threads?api-version=7.1
{
  "comments": [
    { "parentCommentId": 0, "commentType": "text", "content": "<markdown>" }
  ],
  "status": "active"
}
```

Its body carries the Scope / What changed / Regression risk / Verification /
Verdict sections from step 7 above, minus the per-finding detail.

Anchored finding thread:

```json
{
  "comments": [
    { "parentCommentId": 0, "commentType": "text", "content": "<markdown>" }
  ],
  "status": "active",
  "threadContext": {
    "filePath": "/src/lib/botReschedule.ts",
    "rightFileStart": { "line": 42, "offset": 1 },
    "rightFileEnd": { "line": 42, "offset": 1 }
  }
}
```

- `filePath` is repo-relative and **must** start with `/`.
- `rightFile*` anchors to the source (new) side — use it for added or modified
  lines. Use `leftFile*` when commenting on a line the PR deletes.
- `offset` is a 1-based column.
- Anchor blocking findings and file-specific non-blocking ones. Keep general
  observations in the summary thread — a thread per nit is how a bot becomes
  noise.

## Step E — Vote

```json
PUT .../pullRequests/{pullRequestId}/reviewers/{yourIdentityGuid}?api-version=7.1
{ "vote": 10 }
```

| Review outcome | Vote | Meaning |
| --- | --- | --- |
| No findings at all | `10` | Approved |
| No blocking findings, some cleanup | `5` | Approved with suggestions |
| One or more blocking findings | `-5` | Waiting for author |

**Never cast `-10` (rejected).** In ADO that can hard-block the PR under branch
policy, and it is not a call an automated reviewer should make unilaterally.

This is the mapping the automation prompts mean by "mark it as approved (or per
the skill's convention)" — the blocking/non-blocking split from step 6 above is
what drives it. Votes replace rather than accumulate, so on a re-review just
PUT the new value. If the repo has "Reset code reviewer votes when there are
new changes" enabled, your vote clears on each push, which is the desired
behaviour here.

## Step F — Identify yourself

Every comment you post ends with a visible footer, so humans know what wrote
it, and carries a machine-readable marker:

```markdown
<!-- openhands-pr-review:v1:round=2 -->

---
🤖 Automated review · round 2 · comment `/review` after pushing fixes to request another pass.
```

The **author GUID from Step A is the authoritative self-check** — it cannot be
spoofed or lost. The HTML comment is a convenience for recovering the round
number; confirm it actually survives ADO's markdown rendering before relying on
it, and fall back to counting your own authored threads if not.

The footer's mention of `/review` is deliberate: it's how developers discover
the command. It's also why the review-requested automation opens with an author
check — without it, your own footer re-triggers the automation forever.

## Step G — Re-review specifics

1. Find your previous review threads (author GUID from Step A).
2. Diff the current iteration against the one you reviewed last (Step B).
3. For each finding you raised previously, determine whether the new commits
   actually address it. State this explicitly — "resolved", "still open",
   "partially addressed, `x` is fixed but `y` isn't".
4. Close threads you raised that are now genuinely fixed:

```json
PATCH .../pullRequests/{pullRequestId}/threads/{threadId}?api-version=7.1
{ "status": "fixed" }
```

   Only close **your own** threads, and only on real evidence in the diff.
5. Do not re-post a finding that already has an open thread of yours. Reference
   the existing thread instead. Re-posting the same finding each round is the
   fastest way to get the bot muted.

## Do NOT (automation runs)

- Do not emit VS Code markdown file links (`[file.ts:12](src/file.ts#L12)`) in
  a PR comment. They are relative filesystem paths and render as broken links
  in ADO. Anchor with `threadContext` instead.
- Do not post a plain top-level comment via the comments endpoint — the
  automations require threads.
- Do not touch any repository or pull request other than the one in this run's
  event payload.
- Do not push commits or modify code. Every automation path here is
  review-only; a human pushes the fixes.
- Do not vote `-10`, ever.
- Do not claim a Verification section you could not run. Absent a clone, say
  typecheck and tests were not run.
