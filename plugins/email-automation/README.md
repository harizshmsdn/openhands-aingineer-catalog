# Email Automation Plugin

OpenHands plugin to send emails, notifications, and RFQ campaigns autonomously via **Microsoft Entra ID / Microsoft Graph API (OAuth 2.0)** or **Brevo**.

---

## 1. User Experience: Natural Language Azure Work Items (WI)

The primary entrypoint for users is an **Azure Work Item (WI)**. Users **do not write CLI commands or memorize flags**. 

### How Users Prompt the Agent
Users describe what they want to send in plain English in the Work Item description:

- **One-off Email**:
  > *"Send an email to alex@contoso.com informing him that the server migration is scheduled for tonight at 10 PM."*
- **Team Alert / Notification**:
  > *"Send an alert to the devops team that the staging deployment failed due to network timeout."*
- **Vendor RFQ / Bulk Outreach**:
  > *"Find enterprise cloud server providers and send an RFQ for 64GB RAM and 2TB NVMe servers."*

---

## 2. Autonomous Agent Decision Workflow

When triggered by a Work Item, the AI Engineer follows this workflow:

1. **Automatic Sender Resolution**: The agent resolves the user's primary email address from Microsoft Graph using Entra ID credentials. The user is never asked for their sender address.
2. **Template Decision**:
   - **One-Off Email**: Gathers the subject and body directly from the prompt. Generates the email inline—**no template file is written to disk**.
   - **Ready-Made Template**: Uses built-in templates from `templates/` (`alert.html.j2`, `default.html.j2`, `rfq.html.j2`) when matching standard campaign types.
   - **Create New Template**: Only creates a new `.html.j2` file if the user explicitly asks for a reusable template.
3. **No External Blocking**: External recipients (e.g. suppliers, clients, personal accounts) are permitted directly without artificial blocks.
4. **Human Review Artifacts (HITL)**:
   - **Individual / One-off Emails**: The agent executes an internal dry run and responds in the Azure Work Item with a clean **preview of the email** (To, Subject, Body) for review.
   - **Bulk Sends / RFQs**: The agent outputs an attached **`.csv` file** of validated recipients along with a markdown summary table for review.
5. **Confirmation & Dispatch**: When the user replies with a natural language confirmation (*"Approved"*, *"Send it"*, *"Looks good"*), the agent dispatches the email through Microsoft Graph.

---

## 3. Configuration: OpenHands UI Secrets

Configure the following secrets under **Settings $\rightarrow$ Secrets** in the OpenHands Web UI:

| Secret Name (or Alias) | Description | Source in Azure / Entra ID Portal |
| --- | --- | --- |
| `AZURE_CLIENT_ID` / `APP_ID` | Application (Client) ID | Entra ID $\rightarrow$ App registrations $\rightarrow$ Overview |
| `AZURE_TENANT_ID` / `DIRECTORY_ID` | Directory (Tenant) ID | Entra ID $\rightarrow$ Overview |
| `AZURE_CLIENT_SECRET` / `CLIENT_SECRET` | Client Secret Value | Entra ID $\rightarrow$ Certificates & secrets |
| `AZURE_OBJECT_ID` / `AZURE_USER_EMAIL` | Requesting User's Object ID or Email/UPN | Entra ID $\rightarrow$ Users $\rightarrow$ Object ID or Email |
| `BREVO_API_KEY` *(Optional)* | API Key for external transactional provider | Brevo dashboard $\rightarrow$ SMTP & API |

---

## 4. Security & Compliance

### Principle of Least Privilege
To scope permissions to authorized users rather than all tenant mailboxes, apply an Exchange Application Access Policy:
```powershell
New-ApplicationAccessPolicy -AppId "<AZURE_CLIENT_ID>" `
  -PolicyScopeGroupId "AuthorizedUsersGroup@company.com" `
  -AccessRight RestrictAccess `
  -Description "Restrict agent email access to authorized users"
```

### Audit & Archiving
Every dispatched run writes:
- Rendered HTML copies of sent emails to `/workspace/email_archive/`.
- A cryptographic audit manifest (`<timestamp>_manifest.json`) containing timestamps, recipient lists, SHA256 checksums, and delivery statuses.

---

## 5. Backend Dispatcher (Internal Agent Engine)

The AI agent executes `scripts/send_campaign.py` behind the scenes:
- **Direct Body (No Template File)**: `--body "<content>"` wraps plain text or HTML in a clean responsive layout.
- **Template-Based**: `--template templates/<name>.html.j2` renders Jinja2 templates.
- **Dry-Run Output**: Renders previews to console and `email_preview/` before dispatch.
- **Execution Flag**: `--send` actually dispatches via Microsoft Graph API.
