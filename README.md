# OpenHands Catalog

This repo is the shared toolbox for our OpenHands agents. If you want the agent
to know how to do something new, run a specific tool, follow a team
convention, call an internal service; you add it here. You don't touch any
agent's code, and nobody has to rebuild a Docker image.

Every agent on the team points at this repo (pinned to a release tag) and
picks up whatever's published here.

## Contributing something. The short version

1. Make a folder under `plugins/` for your thing.
2. Add one required file: `.plugin/plugin.json`.
3. Add an entry for it in `.plugin/marketplace.json`.
4. Open a PR.
5. Once merged, tag a release.

No agent code changes, no image rebuild and no redeploy. Agents move
to your new plugin whenever *they* bump the tag they're pinned to, it never
happens automatically underneath them.

## What runs your plugin

Plugins in this catalog execute inside a prebuilt sandbox image. You do **not**
build or modify that image to contribute, but you do need to know what is
already in it, because that determines whether your plugin can ship today or
has to wait for an image bump.

### Two clocks

This catalog and the sandbox image are versioned separately and released on
deliberately different cadences. Keeping them independent is the point of the
design: it is what lets you ship a plugin without a rebuild or a redeploy.

| Artifact | Version | Cadence | Changed by |
| --- | --- | --- | --- |
| This catalog | `v0.1.0` | Weekly — whenever a PR merges | Anyone, via PR |
| Sandbox image | `openhands-aingineer-sandbox:v1` | On demand for new root/system tools | Platform owner |

A normal contribution touches only the left column: add a directory under
`plugins/`, add an entry to `marketplace.json`, open a PR, tag a release.
Consumers pick up your
plugin when they bump their pinned `CATALOG_REF`.

### What is already in the image

- `agent-server` 1.58.0 (Python base)
- Azure CLI & Azure Communication Extension
- System tools: `git`, `curl`, `pandoc`, `jq`
- C/C++ build toolchain (`build-essential`)
- Node.js 20.x + `npm` / `npx`
- Miniforge (Conda) at `/opt/conda`
- Python tools: `docling`, `playwright` (with baked-in Chromium), `jinja2`
- `uv` / `uvx`

### The one question to answer before you open a PR

> **Does this plugin need anything installable only as root?**

Before you request an image update, check the **What is already in the image** list above. We have proactively baked in heavy tools like Playwright, Azure CLI, Pandoc, Node, and Docling to avoid cold-start penalties and permissions issues.

The sandbox runs as the unprivileged `openhands` user. That has three
consequences worth internalising, because they decide the answer:

- `apt-get install` **will not work at runtime.** No root, no package manager.
- `/opt/conda` is world-readable but **not writable**, so `conda install` into
  the base environment fails. Create your own prefix instead:
  `conda create -p "$HOME/envs/<name>" …`
- `$HOME` **is** writable. Anything you can install into your home directory (via `uv`, `pip`, or `npm`) is
  fair game at conversation time.

Work down this list and stop at the first option that works. Almost everything
lands on 1 or 2.

**1. Ship it as an MCP server. No image involvement at all.**
If the capability can be expressed as an MCP server launched by `uvx` or `npx`,
declare it in your plugin's `.mcp.json` and you are done. It installs at turn
time. This is the default answer for new capability, and it is the only route
by which an extension's `.mcp.json` is actually wired in — a bare skill's is
loaded and then ignored.

```json
{
  "mcpServers": {
    "my-tool": { "transport": "stdio", "command": "uvx", "args": ["my-mcp-tool"] }
  }
}
```

**2. Install into a conda environment under `$HOME` at conversation time.**
For language runtimes and CLI tools; ruby, a pinned Python, a compiler
toolchain; have your skill create a prefix in `$HOME` on first use. This costs
some seconds on a cold conversation and nothing on an image rebuild. Conda is
in the image precisely so that this route stays open for things nobody
anticipated.

**3. Request an image layer. The slow path.**
Only if 1 and 2 genuinely cannot work: a system library, an apt package, a
setuid binary, anything requiring root. Open an issue labelled `needs-image`
describing what you need and why the first two options fail. Do not open a PR
against the image; these are **batched and shipped quarterly** so that the
image tag stays stable and every consumer is not chasing a moving base.

If you are blocked on a `needs-image` request, say so in the issue. Genuine
blockers get an out-of-band bump, but the default is to wait for the batch,
and most requests turn out to be option 2 in disguise.

### Custom Python tools are out of scope

Tools registered via `register_tool()` run in-process inside the agent-server,
so they must be compiled into the image, which requires a different image
target and an SDK checkout as a permanent build dependency. That moves the
extension point off this catalog's weekly clock and onto the image's quarterly
one, and it is why this catalog does not accept them. Use an MCP server.


## Step by step: adding a plugin

Say you want to add a plugin called `db-tools`.

**1. Create the folder structure**

```
plugins/db-tools/
├── .plugin/
│   └── plugin.json
└── skills/
    └── db-tools/
        └── SKILL.md
```

Only `plugin.json` is required. Everything else, `skills/`, `agents/`,
`commands/`, `hooks/hooks.json`, `.mcp.json` is optional, and you can add
it later without restructuring anything.

**2. Write `plugin.json`**

```json
{
  "name": "db-tools",
  "version": "1.0.0",
  "description": "Helpers for querying and migrating our internal databases",
  "author": {
    "name": "Your Name",
    "email": "you@company.com"
  }
}
```

Only `name` is required. The rest have sensible defaults. `license` and
`repository` are also fine to add if relevant; extra fields don't break
anything.

**3. Write your skill**

`skills/db-tools/SKILL.md` is a normal skill file instructions in Markdown
that tell the agent when and how to use this capability. If you've written a
skill before, this part is identical.

**4. (Optional) Give it an MCP server**

If your plugin needs to talk to a live tool/service (not just shell out to a
CLI), add `.mcp.json` at the plugin root:

```json
{
  "mcpServers": {
    "db-tools": {
      "command": "uvx",
      "args": ["mcp-server-postgres"]
    }
  }
}
```

> **Important:** `.mcp.json` only does anything when it's at the **plugin
> root**, next to `plugin.json`. It does nothing useful inside a bare skill
> folder that isn't part of a plugin. The agent will never connect to that
> server. If your addition needs an MCP server, it must be a plugin, not a
> standalone skill.

**5. Register it in the marketplace index**

Open `.plugin/marketplace.json` at the repo root and add your plugin to the
`plugins` list:

```json
{
  "name": "our-team-catalog",
  "owner": { "name": "Our Team", "email": "team@company.com" },
  "description": "Shared plugins and skills for our OpenHands agents",
  "plugins": [
    {
      "name": "db-tools",
      "source": "./plugins/db-tools",
      "description": "Helpers for querying and migrating our internal databases"
    }
  ],
  "skills": []
}
```

This file is the index. It's how agents discover that `db-tools` exists at
all. Forgetting this step is the most common way a new plugin "silently
doesn't show up."

**6. Open a PR**

Normal review process. Nothing agent-side needs to change for your PR to be
mergeable.

## Releasing a new version

Agents don't automatically get new plugins the moment they're merged to
`main` . They're pinned to a git tag on purpose, so a working setup never
breaks under someone's feet. To actually ship what's in `main`:

```bash
git checkout main
git pull
git tag v0.1.1
git push origin v0.1.1
```

Pick the next version number up from whatever the last tag was. A tag is just a tag, like any other git repo.

Anyone who wants your new plugin now updates the version their agent points
at (usually one line, e.g. `CATALOG_REF = "v0.1.1"`) and redeploys/restarts
their agent. Until they do that, they keep working exactly as before.

## Repo layout

```
openhands-catalog/
├── .plugin/
│   └── marketplace.json      # the index — lists every plugin & skill
└── plugins/
    └── <plugin-name>/
        ├── .plugin/
        │   └── plugin.json   # required: name, version, description, author
        ├── .mcp.json          # optional: MCP servers this plugin provides
        ├── skills/            # optional: one or more SKILL.md files
        ├── agents/            # optional: subagent definitions
        ├── commands/          # optional: slash commands
        └── hooks/
            └── hooks.json     # optional: lifecycle hooks
```

## FAQ

**Do I have to fill in every field?**
No. `plugin.json` only requires `name`. Everything in the folder structure
above besides `plugin.json` itself is optional.

**Can I just add a skill without making it a full plugin?**
Yes — drop it under a `skills:` entry in `marketplace.json` instead of
`plugins:`, pointing at a folder with a `SKILL.md`. Do this if your addition
is pure instructions with no MCP server, hooks, subagents, or slash commands
attached. The moment you need any of those, make it a plugin instead.

**I added `.mcp.json` to my skill folder and it's not working.**
Expected — see the callout above. Move your skill into a plugin folder
structure; `.mcp.json` is only honored at the plugin root.

**How do I know what tag an agent is currently using?**
Ask whoever owns that agent, or check its config for a `CATALOG_REF` (or
similarly named) constant. That's the pinned version it's running against.