---
name: conda-cross-platform-manager
description: >
  Enforces YAML-first approach for managing conda environments and exports clean conda environments to be used by other users regardless of OS.
  Also use this whenever conda itself is missing: if `conda` is not on PATH or a command fails with "conda: command not found", this skill installs
  it. Do not conclude that conda is unavailable, and do not install it by hand, without reading this skill first.
version: "1.0"
compatibility: Requires bash. conda is bootstrapped automatically when absent on Linux sandboxes; on darwin and windows conda must already be installed.
metadata:
  author: ryz
triggers:
  - install package
  - export conda environment
  - save conda environment
  - update environment
  - share environment
  - remove dependency
  - conda not found
  - conda command not found
  - conda is not installed
  - install conda
  - create conda environment
  - conda --version
---

# Conda Cross-Platform Manager

Primary goal is to maintain a clean `environment.yml` file that is free of platform-specific packages, dependencies, and versions. This allows for easy sharing and updating of conda environments across different operating systems. 

## Step 0: Make sure conda exists

`conda` is not guaranteed to be on PATH. Whether it is depends on where this
conversation is running, and you cannot tell without checking.

Run this **before any other conda command in this conversation**:

```bash
S=$(find "$HOME/.openhands/cache/plugins" -name ensure-conda.sh -type f 2>/dev/null | head -1)
[ -n "$S" ] && bash "$S" || echo "ensure-conda.sh not found"
```

The script ships with this plugin, so it is on disk wherever this skill was
loaded from — but the path contains a generated hash, which is why you locate
it rather than hardcode it.

It is idempotent and safe to re-run. What it costs depends on the environment:

- **Self-hosted sandbox** — conda is baked into the image at `/opt/conda`. The
  script finds it and exits immediately. No cost.
- **OpenHands Cloud** — the stock image has no conda, so it installs Miniforge
  under `$HOME/.local/miniforge`. Roughly 30-60 seconds, and it happens **once
  per sandbox**, not once per conversation: a later conversation in the same
  sandbox re-links it in about a second.

Afterwards, verify with `conda --version` before continuing. If the script
prints that it could not be found, or the install fails (usually no network
egress to `github.com`), **stop and report that plainly** — do not improvise an
alternative install. A hand-rolled conda is worse than none, and the failure is
an environment problem the user needs to know about.

### Do not

- Do not write to `/opt/conda` — it is root-owned and deliberately read-only.
  You run as the unprivileged `openhands` user.
- Do not `apt-get install` conda or fetch Miniconda from elsewhere. The
  bootstrap pins the same Miniforge version as the sandbox image so both paths
  behave identically.
- Do not create or modify environments before Step 0 succeeds. `conda: not
  found` partway through a workflow is exactly what this step prevents.

Create environments under `$HOME`, never under `/opt`:

```bash
conda create -y -p "$HOME/envs/<name>" python=3.13
```

## Core Instructions 

Depending on the user's request, follow the approriate workflow to either export a clean environment, update an existing `environment.yml`, or remove unnecessary dependencies.

### Workflow A: Installing, Updating, or Removing Packages (YAML-first approach)

When asked to install, update, or remove a package, use the following workflow:

  1. **Never use imperative commands** like `conda install`, `conda update`, or `conda remove` directly. Instead, always modify the `environment.yml` file first.

  2. **Edit the YAML directly:** Open the `environment.yml` file and add, update, or remove the package from the `dependencies` section. For example, to add a package, include it in the list:
    ```yaml
    dependencies:
      - numpy
      - pandas
      - matplotlib
    ```

  3. **Sync the environment:** Apply the updated YAML file to the existing environment by using a prune flag
    ```bash
    conda env update --file environment.yml --prune
    ```

### Workflow B: Exporting a Clean Environment (OS-agnostic)

When asked to export, save, or capture the current conda environment, use the following workflow:

  1. **Use history:** Never run a raw `conda env export > environment.yml` command. Always use the --from-history flag:
    ```bash
    conda env export --from-history > environment.yml
    ```
  2. **Remove local paths:** After exporting, open the `environment.yml` file and remove the prefix: /path/to/local/env line at the very bottom of the file
  3. **Restore pip packages:** If the project uses pip packages, ensure that the `pip` section is included in the `environment.yml` file. If not, add it manually:
    ```yaml
    dependencies:
      - pip
      - pip:
        - package1
        - package2
    ```


