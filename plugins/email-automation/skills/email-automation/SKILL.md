---
name: email-automation
description: Send templated emails, notification campaigns, and RFQs via Microsoft Graph API (Entra ID OAuth) or Brevo.
version: "2.0"
compatibility: Requires Entra ID secrets in OpenHands UI (App ID, Directory ID, Secret, Object ID) or BREVO_API_KEY.
metadata:
  author: ryz
triggers:
  - send an email
  - notify by email
  - notification simulation
  - generate leads
  - rfq emails
---
# Email Automation

Automated email delivery via Microsoft Graph API (OAuth 2.0) and Brevo.

## Core Rules
- **Automatic Sender**: Sender is locked to the requesting user's email, auto-resolved via Entra ID `OBJECT_ID`. **Never ask the user for a sender address.**
- **Scope**: Recipients must match sender domain or allowlist. Bypass for external outreach using `--transactional`.
- **HITL (Human in the Loop)**: Always execute dry run first. Present preview payloads and pause for user confirmation before `--send`.
- **Compliance**: Never delete archive manifests or rendered `.html` payloads.

## 1. Lead Generation Workflow (RFQs)
1. **Discover**: Search target domains via search tool. Save to `domains.csv`.
2. **Extract**: `python scripts/extract_emails.py --input domains.csv --output leads.csv`
3. **Validate**: `python scripts/validate_leads.py --input leads.csv --output leads_validated.csv`
4. **Template**: Pick/create template in `plugins/email-automation/templates/*.j2`.
5. **Preview**: Run dry run without `--send`.
6. **HITL Pause**: Present sample and ask user for confirmation.
7. **Send**: Run with `--transactional --send`.

## 2. Notification Workflow
1. Select template (`.j2`) and recipients (`.csv`, `.json`, or `--to`).
2. **Dry Run (Required)**: Render payloads and inspect scope.
3. **HITL Pause**: Wait for user confirmation.
4. **Send**: Run with `--send` (add `--confirm-bulk` if >50 recipients).

## Execution CLI

```bash
SEND=$(find "$HOME/.openhands/cache/plugins" . -name send_campaign.py -type f 2>/dev/null | head -1)

# Dry run (Sender auto-resolved from Entra ID)
python "$SEND" --template alert.j2 --recipients reps.csv --subject "Notification"

# Send via Microsoft Graph (Default)
python "$SEND" --template alert.j2 --recipients reps.csv --subject "Notification" --send

# Send Transactional / RFQ
python "$SEND" --template rfq.j2 --recipients leads.csv --subject "RFQ" --transactional --send

# Inline recipients (Quick send)
python "$SEND" --template alert.j2 --to alice@domain.com --subject "Direct Alert" --send
```
