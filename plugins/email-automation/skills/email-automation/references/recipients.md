# Recipients & Authentication Reference

## Recipients Formats
- **CSV/JSON**: Requires `email` column; extra columns pass as template variables.
- **Inline**: Pass `--to <email1> <email2>`.

## Sender Identity & Authentication
- **Sender**: Auto-resolved from Entra ID (`OBJECT_ID` or user email).
- **Entra ID Secrets**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_OBJECT_ID`.
- **External Scope**: Permitted directly; human review of the preview or CSV provides safety.

## Audit Records
Dispatched sends save HTML payloads to `/workspace/email_archive/` and write `<timestamp>_manifest.json` with delivery records.
