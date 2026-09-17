# Recipients, Scope, and Manifest Reference

Reference documentation for `send_campaign.py`.

## Recipients File
CSV or JSON with an `email` column. Other columns map to Jinja2 template variables.
```csv
email,first_name,department
alice@company.com,Alice,Finance
```
Small ad-hoc sends can use inline addresses: `--to alice@company.com bob@company.com`.

## Sender Identity & Scope
- **Sender Auto-Resolution**: The agent queries Microsoft Graph using the requesting user's Entra ID `OBJECT_ID`. It automatically sets the sender to the user's primary email address (`mail` or `userPrincipalName`).
- **Scope Checking**: Unmatched recipients outside the sender domain or allowlist are rejected.
  1. **Sender Domain (Default)**: `*@<sender-domain>`
  2. **`EMAIL_ALLOWLIST`**: Env variable (comma-separated).
  3. **Allowlist Files**: `/workspace/email_allowlist.txt` or `plugins/email-automation/allowlist.txt`.
- **Transactional Bypass**: Use `--transactional` for external communications (such as RFQs) to bypass allowlist boundaries.

## Providers
- **Microsoft Graph / Entra ID (Default)**: OAuth 2.0 Client Credentials flow using OpenHands secrets:
  - App (Client) ID (`AZURE_CLIENT_ID` / `APP_ID`)
  - Directory (Tenant) ID (`AZURE_TENANT_ID` / `DIRECTORY_ID`)
  - Client Secret (`AZURE_CLIENT_SECRET` / `CLIENT_SECRET`)
  - User Object ID (`AZURE_OBJECT_ID` / `OBJECT_ID`)
- **Brevo**: Pass `--provider brevo`. Requires `BREVO_API_KEY`.

## Manifest & Compliance
Every real send writes a timestamped audit record (`<archive-dir>/<timestamp>_manifest.json`) and copies of rendered `.html` payloads. Never delete these records.
