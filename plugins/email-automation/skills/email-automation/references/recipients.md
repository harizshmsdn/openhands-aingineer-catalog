# Recipients & Authentication Reference

## Recipients Formats
- **CSV/JSON**: Requires `email` column; extra columns pass as template variables.
- **Inline**: Pass `--to <email1> <email2>`.

## Sender Identity & Authentication
- **Sender**: Auto-resolved from the Azure Work Item creator (`System.CreatedBy` or `--sender <creator_email>`), falling back to Entra ID env (`AZURE_WORK_ITEM_CREATOR`, `AZURE_USER_EMAIL`, `AZURE_OBJECT_ID`).
- **Entra ID Secrets**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`.
- **External Scope**: Permitted directly; human review of the preview or CSV provides safety.

## Sent Items & Audit Records
- **Sent Items**: Single sends (`<= 5`) preserve emails to the sender's Outlook Sent Items; bulk sends (`> 5`) disable this to prevent inbox clutter (override with `--save-to-sent` or `--no-save-to-sent`).
- **Audit Archive**: Dispatched sends save HTML payloads to `/workspace/email_archive/` and write `<timestamp>_manifest.json` with delivery records.
