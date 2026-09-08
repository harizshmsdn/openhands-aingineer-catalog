---
name: email-automation
description: >
  Send templated/personalized emails and run authorized internal
  security-awareness (phishing-simulation) campaigns via Azure Communication
  Services.
version: "1.0"
compatibility: >
  Requires the Azure CLI (`az`) with the `communication` extension, an ACS
  resource, a verified sender domain, and jinja2. Auth via
  AZURE_COMMUNICATION_CONNECTION_STRING, --connection-string, or `az login`.
metadata:
  author: ryz
triggers:
  - send an email
  - send email
  - email the team
  - email these people
  - notify by email
  - bulk email
  - render email template
  - phishing simulation
  - security awareness campaign
  - awareness training email
---

# Email Automation

Send templated emails and run **authorized** security-awareness
(phishing-simulation) campaigns. All rendering, scope-checking, dry-run, send,
and archiving is done by `scripts/send_campaign.py`; this file covers when and
how to drive it. Format details live in [references/recipients.md](references/recipients.md).

## Rules of engagement (read first)

Legitimate uses: (1) transactional/notification email, and (2) phishing
simulations, but **only** against your **own organization's** users with prior
sign-off. Hard boundaries:

- **Owned, verified sender only.** The sender must be a domain you own and
  verified in ACS. Do not spoof, register, or send from a look-alike domain
  impersonating another company, brand, or person. That is fraud, not a
  simulation; decline and explain if asked.
- **In-scope recipients only.** Every recipient must match the resolved
  allowlist (see references). Out-of-scope addresses stop the run.
- **Keep the record.** Never delete the archived payloads or manifest.

If any boundary can't be met, stop and tell the user rather than improvising.

## Workflow

1. **Gather** from the prompt: sender (owned/verified; ask if missing), subject,
   scenario, and recipients. Recipients come from a workspace CSV/JSON file
   (preferred, and required for personalization) or a few inline addresses; see
   [references/recipients.md](references/recipients.md) for the format. Never
   invent or expand a list. For simulations, capture who authorized it.
2. **Author** the HTML template. `jinja2` variables map to the non-`email`
   columns of the recipients file (e.g. `{{ first_name }}`).
3. **Dry run (mandatory).** Run the script with no `--send`. It renders one
   payload per recipient, flags any out-of-scope addresses, and prints a
   summary. Show the user the sender, recipient count/list, subject, and a
   rendered payload, then wait for **explicit confirmation**. A dry run alone is
   a valid outcome when the user just wants a preview.
4. **Send** only after confirmation, by re-running with `--send`. The script
   refuses out-of-scope recipients, requires `--confirm-bulk` above 50, verifies
   auth, sends per recipient, archives payloads, and writes a manifest. It never
   silently retries: on failure it records the exact error and reports it.

**Locate the script first.** It ships with this plugin, but the install path
contains a generated hash, so find it rather than hardcoding a path (the same
convention the conda plugin uses):

```bash
SEND=$(find "$HOME/.openhands/cache/plugins" -name send_campaign.py -type f 2>/dev/null | head -1)
[ -z "$SEND" ] && SEND=$(find . -path '*email-automation/scripts/send_campaign.py' -type f 2>/dev/null | head -1)
[ -z "$SEND" ] && { echo "send_campaign.py not found"; exit 1; }
```

Then drive it:

```bash
# dry run (default): render + summarize, nothing sent
python "$SEND" --template alert.html.j2 \
  --recipients /workspace/recipients.csv \
  --sender no-reply@yourdomain.com --subject "Security notice"

# send, after the user confirms the dry-run summary
python "$SEND" --template alert.html.j2 \
  --recipients /workspace/recipients.csv \
  --sender no-reply@yourdomain.com --subject "Security notice" \
  --scenario password-reset --authorizer jane@yourdomain.com --send
```

Recipient scope defaults to the verified sender's own domain; set
`EMAIL_ALLOWLIST` (comma-separated) only to send beyond it. Run
`python "$SEND" --help` for all flags. `references/recipients.md` sits next to
this file; read it for the recipients-file, allowlist, and manifest formats.
