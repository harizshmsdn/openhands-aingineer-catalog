#!/usr/bin/env bash
# Ensure `conda` is available, wherever this agent happens to be running.
#
# Target-aware and idempotent, in three tiers:
#   1. conda already on PATH        -> no-op   (self-hosted image: instant)
#   2. previously bootstrapped here -> re-link (same sandbox, later conversation)
#   3. nothing                      -> install (OpenHands Cloud: ~30-60s, once)
#
# Why this exists: OpenHands Cloud's sandbox spec catalogue is read-only and
# holds only the stock agent-server image, so a custom conda image cannot be
# registered. Conda must therefore be installed at run time there. On the
# self-hosted image it is already baked in at /opt/conda and tier 1 exits
# immediately, so this script costs nothing on that path.
#
# Runs as the unprivileged `openhands` user: installs under $HOME, never
# touches /opt/conda (which is root-owned and read-only by design).
#
# Usage:  bash scripts/ensure-conda.sh   (safe to run repeatedly)

set -euo pipefail

# Keep in step with the Dockerfile's ARG MINIFORGE_VERSION so both paths
# converge on the same conda.
MINIFORGE_VERSION="${MINIFORGE_VERSION:-24.11.3-2}"
PREFIX="${CONDA_BOOTSTRAP_PREFIX:-$HOME/.local/miniforge}"

log() { printf '[ensure-conda] %s\n' "$*" >&2; }

# --- Tier 1: already on PATH (self-hosted image) ---------------------------
if command -v conda >/dev/null 2>&1; then
  log "conda already present: $(command -v conda) ($(conda --version 2>/dev/null || echo '?'))"
  exit 0
fi

# --- Tier 2: bootstrapped earlier in this sandbox -------------------------
# One sandbox hosts many conversations, so the install is paid once per
# sandbox rather than once per conversation.
if [ -x "$PREFIX/bin/conda" ]; then
  log "reusing existing bootstrap at $PREFIX"
else
  # --- Tier 3: install -----------------------------------------------------
  # Only sandboxes are bootstrapped. On a developer's own machine, silently
  # installing a second conda would be rude and probably wrong — say so and
  # let them choose.
  if [ "$(uname -s)" != "Linux" ]; then
    log "conda not found, and automatic bootstrap only supports Linux sandboxes."
    log "This looks like $(uname -s). Install conda yourself, e.g. via miniforge:"
    log "  https://github.com/conda-forge/miniforge#install"
    exit 1
  fi

  case "$(uname -m)" in
    x86_64) MC=x86_64 ;;
    aarch64 | arm64) MC=aarch64 ;;
    *) log "unsupported architecture: $(uname -m)"; exit 1 ;;
  esac

  URL="https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-${MINIFORGE_VERSION}-Linux-${MC}.sh"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT

  log "installing miniforge ${MINIFORGE_VERSION} (${MC}) into $PREFIX"
  if ! curl -fsSL --retry 3 --retry-delay 2 -o "$TMP/mf.sh" "$URL"; then
    log "download failed — the sandbox may have no network egress to github.com"
    exit 1
  fi
  # -b batch, -p prefix. No -u: refuse to silently overwrite a partial install.
  bash "$TMP/mf.sh" -b -p "$PREFIX"
  "$PREFIX/bin/conda" clean -afy >/dev/null 2>&1 || true
fi

# --- Persist on PATH for later shells -------------------------------------
# Each tool call may open a fresh shell, so exporting PATH here is not enough:
# without this the next command would report "conda: not found" again.
LINE="export PATH=\"$PREFIX/bin:\$PATH\""
for RC in "$HOME/.bashrc" "$HOME/.profile"; do
  if [ -f "$RC" ] && grep -qF "$LINE" "$RC" 2>/dev/null; then
    continue
  fi
  printf '\n# added by ensure-conda.sh\n%s\n' "$LINE" >> "$RC"
done

export PATH="$PREFIX/bin:$PATH"

# --- Verify ---------------------------------------------------------------
if ! command -v conda >/dev/null 2>&1; then
  log "bootstrap finished but conda is still not on PATH — check $PREFIX"
  exit 1
fi
log "ready: $(conda --version)"
log "new shells pick this up via ~/.bashrc; in THIS shell run:"
log "  export PATH=\"$PREFIX/bin:\$PATH\""