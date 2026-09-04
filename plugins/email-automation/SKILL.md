---
name: email-automation
description: Instructions for sending automated emails using Azure Communication Services
---

# Email Automation

You are equipped to send dynamic emails and conduct targeted phishing simulations using the Azure CLI (`az communication email send`), which is pre-installed in your sandbox. 

Follow these steps when the user asks you to send an email or run a simulation.

## 1. Understand the Request
Extract the following details from the user's prompt:
- **Sender Address**: Must be specified by the user (e.g., a lookalike domain for phishing, or the standard company domain). If not provided, explicitly ask the user for it.
- **Recipients**: Identify the target email addresses. Can be a single user or a bulk list.
- **Subject**: The subject line of the email.
- **Content/Scenario**: The premise of the email. Is it a security alert, a fake password reset, or a standard notification?

## 2. Prepare the Email Content
- For phishing simulations or rich notifications, you must generate an HTML template.
- You have `jinja2` available in your Python environment. For bulk sends or dynamic personalization, write a short Python script to render the HTML.
- Save the final rendered HTML to a file in your workspace (e.g., `/workspace/email_payload.html`).

## 3. Execute the Delivery
Use the Azure CLI to dispatch the email. 

```bash
az communication email send \
  --sender "<SENDER_ADDRESS>" \
  --to "<RECIPIENT_1>" "<RECIPIENT_2>" \
  --subject "<EMAIL_SUBJECT>" \
  --body-html "$(< /workspace/email_payload.html)"
```

*Note: For complex or very large HTML bodies, it is recommended to use Python's `subprocess` module to execute the `az` command to avoid bash character-escaping issues.*

## 4. Cleanup
- Once the email is successfully dispatched, delete the temporary HTML file (e.g., `rm /workspace/email_payload.html`) to keep the workspace clean.

## 5. Error Handling & Rules of Engagement
- **Do not bypass permissions**: Treat the recipient list provided by the user as absolute.
- **Handling Failures**: If the `az communication email` command fails (e.g., due to an unverified domain or missing connection string), DO NOT silently retry. Log the exact error output and report it back to the user or Azure DevOps work item immediately.
