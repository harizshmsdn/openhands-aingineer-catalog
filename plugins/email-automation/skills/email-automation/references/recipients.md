# Recipients, scope, and manifest formats

Detail for `send_campaign.py`. Read this when you need to build a recipients
file, configure the allowlist, or inspect an archived campaign.

## Recipients file

Preferred for anything beyond a couple of addresses, and required for
personalization. Point the script at it with `--recipients PATH`.

CSV with an `email` column plus any columns you want as template variables:

```csv
email,first_name,department
alice@yourdomain.com,Alice,Finance
bob@yourdomain.com,Bob,Engineering
```

JSON is equivalent, a list of objects each with at least `email`:

```json
[{"email": "alice@yourdomain.com", "first_name": "Alice", "department": "Finance"}]
```

Non-`email` columns become jinja2 variables, so `Hi {{ first_name }}` in the
template (or subject) fills from the `first_name` column. The script renders one
payload per recipient and sends them individually, so each person gets their own
values.

For a few ad-hoc addresses you can skip the file and pass `--to a@x b@x`
instead. Never invent or expand a list; use exactly what the user provided.

## Allowlist (scope)

Every recipient must be in scope. The script resolves scope in three tiers,
first match wins, and you usually configure nothing:

1. **Verified sender domain (default).** The sender is a domain you own and
   verified in ACS, so `*@<sender-domain>` is allowed automatically. Emailing
   your own org from your own domain needs zero setup.
2. **`EMAIL_ALLOWLIST` env var**, comma-separated, for sending beyond the
   sender's domain (contractors, a second brand). Set it next to
   `AZURE_COMMUNICATION_CONNECTION_STRING`. Never commit it.
3. **A gitignored file**, if you prefer a file to an env var. The script checks
   `/workspace/email_allowlist.txt` then `plugins/email-automation/allowlist.txt`
   (both gitignored; `allowlist.example.txt` documents the format).

Each entry is a full address (`alice@yourdomain.com`) or a domain wildcard
(`*@yourdomain.com`). Lines starting with `#` are comments. Any recipient
matching no tier is out of scope: the script lists them and refuses to send.
Keep org-specific domains out of the public repo; use the sender default or the
env var.

## Manifest

On a real send the script writes `<archive-dir>/<timestamp>_manifest.json` and
archives every sent payload. The manifest records: `timestamp`, `sender`,
`subject`, `scenario`, `authorizer`, `recipient_count`, `recipients_sha256`,
the full `recipients` list, `sent`, and `failed` (with the exact per-recipient
error). This is the audit record for click-tracking correlation, compliance,
and after-action review. Do not delete it.
