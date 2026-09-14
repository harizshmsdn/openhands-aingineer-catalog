---
name: email-automation
description: Send templated emails, run phishing simulations, and generate leads via Azure/Brevo.
version: "1.0"
compatibility: Requires Azure CLI or BREVO_API_KEY, and jinja2.
metadata:
  author: ryz
triggers:
  - send an email
  - notify by email
  - phishing simulation
  - generate leads
  - rfq emails
---
# Email Automation
Core script: `scripts/send_campaign.py`. Format details: `references/recipients.md`.

## Rules
- **Authorized Only**: Sender must be an owned, verified domain. No spoofing.
- **Scope**: Recipients must match allowlist (default: sender's domain).
- **Exceptions**: External transactional emails (e.g., RFQs) bypass allowlist via `--transactional`.
- **Audit**: Never delete archived payloads or manifest.

## 1. Lead Gen Workflow (HITL)
For transactional OSINT (e.g. RFQs):
1. **Discover**: Use `duckduckgo_search` to find target domains. Save as `domains.csv`.
2. **Extract**: Run `python scripts/extract_emails.py --input domains.csv --output leads.csv` (Auto-runs Tier 2A scrape + 2B theHarvester fallback).
3. **Validate**: Run `python scripts/validate_leads.py --input leads.csv --output leads_validated.csv` (Filters dead MX).
4. **Template**: Fetch/modify from `plugins/email-automation/templates`. (Create `.j2` dynamically if missing).
5. **HITL Check**: **Pause for user confirmation on `leads_validated.csv`**.
6. **Send**: Run `send_campaign.py` with `--transactional --provider brevo`.

## 2. Standard/Phishing Workflow
1. **Gather**: Sender, subject, recipients (CSV/JSON), scenario.
2. **Template**: `.j2` variables map to CSV columns.
3. **Dry Run (Mandatory)**: Render payloads & verify scope (no `--send`). **Wait for user confirmation.**
4. **Send**: Execute with `--send`. Requires `--confirm-bulk` if >50 recipients.

## Execution
```bash
SEND=$(find "$HOME/.openhands/cache/plugins" . -name send_campaign.py -type f 2>/dev/null | head -1)

# Dry run (Preview)
python "$SEND" --template alert.j2 --recipients reps.csv --sender x@dom.com --subject "Hi"

# Send (Phishing/Internal)
python "$SEND" --template alert.j2 --recipients reps.csv --sender x@dom.com --subject "Hi" --send

# Send (Lead Gen / Brevo)
python "$SEND" --template rfq.j2 --recipients leads.csv --sender x@dom.com --subject "RFQ" --provider brevo --transactional --send
```
