---
name: email-automation
description: Send emails, notifications, and RFQ campaigns from natural language Azure Work Item prompts via Microsoft Graph API (Entra ID OAuth) or Brevo.
version: "2.2"
metadata:
  author: ryz
triggers:
  - send an email
  - email someone
  - notify by email
  - rfq emails
---
# Email Automation

Autonomously process email requests from natural language Azure Work Items (WI) via Microsoft Graph API.

## Rules
- **No CLI For Users**: Users provide plain English prompts only. Never ask users for CLI flags (`--send`, `--template`, `--body`) or commands.
- **Auto Sender**: Resolved via Entra ID (`OBJECT_ID` or user email). Never prompt for sender.
- **No External Block**: External recipients are allowed directly.
- **HITL (Human in the Loop)**: Always dry run first. Present review artifact and wait for user approval before dispatch.

## Decision Matrix
1. **One-Off Email**: Extract recipient, subject, body from prompt. Run dry run with `--body` (no `.j2` template file on disk). Reply in WI with formatted preview (To, Subject, Body) asking confirmation.
2. **Ready Template**: For standard notices/alerts/RFQs, use `templates/{alert,default,rfq}.html.j2`.
3. **New Template**: Save `templates/<name>.html.j2` only when explicitly requested by user.
4. **Bulk / RFQ**: Discover/extract leads to CSV. Reply in WI with `.csv` path and recipient summary table for review.

## Commands (Internal Agent Use)
```bash
# One-off dry run (no template file)
python scripts/send_campaign.py --to "<to>" --subject "<subject>" --body "<content>"

# Template dry run
python scripts/send_campaign.py --template templates/<tpl>.html.j2 --to "<to>" --subject "<subject>"

# Bulk RFQ dry run
python scripts/send_campaign.py --template templates/rfq.html.j2 --recipients <file>.csv --subject "<subject>"

# Dispatch (run after user confirms: "Approved" / "Send")
python scripts/send_campaign.py [same arguments] --send
```
