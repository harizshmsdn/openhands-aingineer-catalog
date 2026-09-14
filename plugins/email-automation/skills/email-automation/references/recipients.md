# Recipients, scope, and manifest formats

Detail for `send_campaign.py`.

## Recipients File
CSV or JSON with an `email` column. Other columns become jinja2 variables.
```csv
email,first_name,department
alice@dom.com,Alice,Finance
```
Agent generates this during Lead Gen. Small sends can use `--to a@x.com`.

## Allowlist (Scope)
Unmatched recipients are rejected. Resolved via:
1. **Verified sender domain (default)**: `*@<sender-domain>`.
2. **`EMAIL_ALLOWLIST`**: Env var (comma-separated).
3. **Files**: `/workspace/email_allowlist.txt` or `plugins/email-automation/allowlist.txt`.

**Bypass**: Use `--transactional` for external business emails (like RFQs) to skip allowlist checks. Not for phishing.

## Providers
- **Azure (Default)**: Uses `az communication email send`. Requires `AZURE_COMMUNICATION_CONNECTION_STRING` or `az login`.
- **Brevo**: Pass `--provider brevo`. Requires `BREVO_API_KEY`. Uses standard HTTP requests.

## Manifest
A manifest (`<archive-dir>/<timestamp>_manifest.json`) and full HTML payload archives are generated on every real send for audit and compliance. Do not delete.
