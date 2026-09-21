#!/usr/bin/env python3
import argparse, csv, hashlib, json, os, pathlib, random, re, sys, time
import urllib.request, urllib.error, urllib.parse

try:
    from jinja2 import Environment, select_autoescape
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

BULK_THRESHOLD = 50


# Determine writable directory for previews and archives
def resolve_default_dir(name):
    ws = pathlib.Path("/workspace")
    if ws.is_dir() and os.access(str(ws), os.W_OK):
        return str(ws / name)
    return str(pathlib.Path.cwd() / name)


# Retrieve first matching environment variable
def get_env(*keys, default=None):
    for k in keys:
        v = os.environ.get(k)
        if v and v.strip():
            return v.strip()
    return default


# Load recipients from CSV, JSON, or inline arguments
def load_recipients(path, inline):
    if inline:
        return [{"email": e.strip()} for e in inline if e.strip()]
    p = pathlib.Path(path)
    text = p.read_text()
    if p.suffix.lower() == ".json":
        rows = json.loads(text)
    else:
        rows = list(csv.DictReader(text.splitlines()))
    out = []
    for r in rows:
        email = (r.get("email") or "").strip()
        if email:
            out.append({k: (v or "").strip() if isinstance(v, str) else v
                        for k, v in r.items()} | {"email": email})
    return out


# Render Jinja2 template with context
def render(env, template_src, context):
    return env.from_string(template_src).render(**context)


# Strip HTML tags and styling for token-efficient preview
def to_plain_text(html_text):
    clean = re.sub(r"<(style|head|script)[^>]*>.*?</\1>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", " ", clean)
    return " ".join(clean.split())


# Request OAuth2 client credentials token from Entra ID
def get_graph_token(tenant_id, client_id, client_secret):
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["access_token"]
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        sys.exit(f"OAuth error ({e.code}): {err}")


# Fetch verified email for user from Microsoft Graph
def get_user_email_from_graph(token, sender_identifier):
    quoted_id = urllib.parse.quote(sender_identifier, safe="")
    url = f"https://graph.microsoft.com/v1.0/users/{quoted_id}?$select=mail,userPrincipalName,displayName,id"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            email = data.get("mail") or data.get("userPrincipalName")
            if not email:
                sys.exit(f"Could not determine email for user: {sender_identifier}")
            return email
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        sys.exit(f"Graph user lookup error ({e.code}) for '{sender_identifier}': {err}")


# Dispatch email message via Microsoft Graph API with retry backoff
def send_via_graph(token, sender_id, to_email, subject, html_body, save_to_sent=True, max_retries=3):
    quoted_sender = urllib.parse.quote(sender_id, safe="")
    url = f"https://graph.microsoft.com/v1.0/users/{quoted_sender}/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}]
        },
        "saveToSentItems": bool(save_to_sent)
    }
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return True, None
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 504) and attempt < max_retries - 1:
                retry_after = e.headers.get("Retry-After")
                wait_time = min(30.0, float(retry_after)) if retry_after and retry_after.isdigit() else (2 ** attempt) + random.uniform(0.5, 1.5)
                time.sleep(wait_time)
                continue
            err = f"HTTP Error {e.code}: {e.read().decode('utf-8')}"
            return False, err
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.0 + attempt)
                continue
            return False, str(e)
    return False, "Max retries exceeded"


# Send email via Brevo REST API
def send_via_brevo(api_key, sender, to_email, subject, html_body):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"email": sender},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return True, None
    except urllib.error.HTTPError as e:
        error_msg = f"HTTP Error {e.code}: {e.read().decode('utf-8')}"
        return False, error_msg
    except Exception as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser(description="Render/send email campaigns via Microsoft Graph or Brevo.")
    ap.add_argument("--template", help="path to the HTML (jinja2) template")
    ap.add_argument("--body", help="inline email body content (HTML or plain text)")
    ap.add_argument("--sender", help="sender email/UPN (e.g. from Azure Work Item creator)")
    ap.add_argument("--subject", required=True, help="subject line (may use jinja2 vars)")
    ap.add_argument("--recipients", help="recipients CSV or JSON file")
    ap.add_argument("--to", nargs="*", help="inline recipient addresses (small sends)")
    ap.add_argument("--scenario", default="", help="scenario label for the manifest")
    ap.add_argument("--authorizer", default="", help="who approved this (simulations)")
    ap.add_argument("--archive-dir", default=resolve_default_dir("email_archive"))
    ap.add_argument("--preview-dir", default=resolve_default_dir("email_preview"))
    ap.add_argument("--send", action="store_true", help="actually send (default: dry run)")
    ap.add_argument("--confirm-bulk", action="store_true", help="ack a >%d send" % BULK_THRESHOLD)
    ap.add_argument("--provider", choices=["graph", "azure", "brevo"], default="graph",
                    help="provider: graph (Microsoft Graph/Entra, default) or brevo")
    ap.add_argument("--save-to-sent", action="store_true", default=None, help="save dispatched email to Sent Items")
    ap.add_argument("--no-save-to-sent", action="store_true", help="do not save dispatched email to Sent Items")
    ap.add_argument("--delay", type=float, default=None, help="delay in seconds between sends")
    args = ap.parse_args()

    # Map legacy azure provider to graph
    if args.provider == "azure":
        args.provider = "graph"

    if not args.recipients and not args.to:
        sys.exit("provide --recipients FILE or --to addr [addr ...]")

    if not args.template and not args.body:
        sys.exit("provide either --template PATH or --body 'content'")

    graph_token = None

    # Resolve sender identity from Microsoft Graph API using Entra ID credentials
    if args.provider == "graph":
        tenant_id = get_env("AZURE_TENANT_ID", "ENTRA_TENANT_ID", "DIRECTORY_ID")
        client_id = get_env("AZURE_CLIENT_ID", "ENTRA_CLIENT_ID", "APP_ID")
        client_secret = get_env("AZURE_CLIENT_SECRET", "ENTRA_CLIENT_SECRET", "CLIENT_SECRET")
        sender_target = args.sender or get_env(
            "AZURE_WORK_ITEM_CREATOR", "WI_CREATOR_EMAIL", "SYSTEM_CREATEDBYEMAIL",
            "AZURE_USER_EMAIL", "AZURE_OBJECT_ID", "ENTRA_OBJECT_ID", "OBJECT_ID",
            "USER_OBJECT_ID", "AZURE_UPN", "USER_PRINCIPAL_NAME"
        )

        if not all([tenant_id, client_id, client_secret]):
            if args.send:
                sys.exit("Missing Entra ID secrets in environment: requires App ID, Directory ID, and Secret")
            elif not sender_target:
                sender_target = "work-item-creator@company.internal"

        if not sender_target:
            if args.send:
                sys.exit("Sender unknown: specify --sender <creator_email> or configure AZURE_WORK_ITEM_CREATOR")
            sender_target = "work-item-creator@company.internal"

        if all([tenant_id, client_id, client_secret]) and sender_target != "work-item-creator@company.internal":
            graph_token = get_graph_token(tenant_id, client_id, client_secret)
            args.sender = get_user_email_from_graph(graph_token, sender_target)
        else:
            args.sender = sender_target
    elif not args.sender:
        sys.exit("--sender required when using non-graph provider")

    recipients = load_recipients(args.recipients, args.to)
    if not recipients:
        sys.exit("no recipients found")

    # Determine Sent Items preservation setting
    if args.no_save_to_sent:
        save_to_sent = False
    elif args.save_to_sent:
        save_to_sent = True
    else:
        save_to_sent = len(recipients) <= 5

    # Determine rate limiting inter-request delay
    if args.delay is not None:
        delay_sec = max(0.0, args.delay)
    elif len(recipients) > 5:
        delay_sec = 1.0
    else:
        delay_sec = 0.0

    # Load template from file or construct HTML from body
    if args.template:
        template_src = pathlib.Path(args.template).read_text()
    else:
        if "<html" in args.body.lower() or "<p>" in args.body.lower() or "<div>" in args.body.lower():
            template_src = args.body
        else:
            paragraphs = "".join(f"<p>{p.strip()}</p>" for p in args.body.split("\n\n") if p.strip())
            template_src = (
                "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
                "<style>body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; "
                "line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px; }</style>\n"
                "</head>\n<body>\n" + (paragraphs or f"<p>{args.body}</p>") + "\n</body>\n</html>"
            )

    env = Environment(autoescape=select_autoescape(["html", "xml"]))

    # Render payloads for previews and archiving
    out_dir = pathlib.Path(args.preview_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for r in recipients:
        body = render(env, template_src, r)
        subject = render(env, args.subject, r)
        path = out_dir / (r["email"].replace("/", "_") + ".html")
        path.write_text(body)
        rendered.append({"email": r["email"], "subject": subject,
                         "body": body, "path": str(path)})

    if not args.send:
        preview_text = to_plain_text(rendered[0]["body"])
        if len(preview_text) > 300:
            preview_text = preview_text[:300] + "..."
        to_str = ", ".join(r["email"] for r in recipients[:3])
        if len(recipients) > 3:
            to_str += f" (+{len(recipients) - 3} more)"
        print(f"[DRY RUN] Sender: {args.sender}")
        print(f"[DRY RUN] To: {to_str} ({len(recipients)} recipient{'s' if len(recipients) != 1 else ''})")
        print(f"[DRY RUN] Save to Sent Items: {save_to_sent}")
        print(f"Subject: {rendered[0]['subject']}")
        print(f"Body: {preview_text}")
        print(f"Payload: {rendered[0]['path']}")
        return 0

    print(f"Sending as {args.sender} to {len(recipients)} recipient(s)...")

    if len(recipients) > BULK_THRESHOLD and not args.confirm_bulk:
        sys.exit(f"{len(recipients)} recipients exceeds {BULK_THRESHOLD}; pass --confirm-bulk")

    archive = pathlib.Path(args.archive_dir)
    archive.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    sent, failed = [], []

    # Dispatch loop for rendered emails
    for idx, r in enumerate(rendered):
        if idx > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        if args.provider == "graph":
            success, err = send_via_graph(graph_token, args.sender, r["email"], r["subject"], r["body"], save_to_sent=save_to_sent)
            if success:
                sent.append(r["email"])
                (archive / f"{ts}_{r['email'].replace('/', '_')}.html").write_text(r["body"])
            else:
                failed.append({"email": r["email"], "error": err})
        elif args.provider == "brevo":
            api_key = get_env("BREVO_API_KEY")
            if not api_key:
                sys.exit("BREVO_API_KEY environment variable is required for Brevo")
            success, err = send_via_brevo(api_key, args.sender, r["email"], r["subject"], r["body"])
            if success:
                sent.append(r["email"])
                (archive / f"{ts}_{r['email'].replace('/', '_')}.html").write_text(r["body"])
            else:
                failed.append({"email": r["email"], "error": err})

    # Save manifest for auditing
    emails = [r["email"] for r in recipients]
    manifest = {
        "timestamp": ts, "sender": args.sender, "subject": args.subject,
        "scenario": args.scenario, "authorizer": args.authorizer,
        "recipient_count": len(recipients), "save_to_sent": save_to_sent,
        "recipients_sha256": hashlib.sha256(",".join(sorted(emails)).encode()).hexdigest(),
        "recipients": emails, "sent": sent, "failed": failed,
    }
    (archive / f"{ts}_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nsent {len(sent)}, failed {len(failed)}. manifest: {archive}/{ts}_manifest.json")
    for f in failed:
        print(f"  FAILED {f['email']}: {f['error']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
