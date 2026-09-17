#!/usr/bin/env python3
import argparse, csv, hashlib, json, os, pathlib, sys, time
import urllib.request, urllib.error, urllib.parse

try:
    from jinja2 import Environment, select_autoescape
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

BULK_THRESHOLD = 50
ALLOWLIST_FILES = ["/workspace/email_allowlist.txt",
                   "plugins/email-automation/allowlist.txt",
                   "email_allowlist.txt"]


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


# Resolve allowed recipient domains and addresses
def load_allowlist(sender):
    entries = set()
    if sender and "@" in sender:
        entries.add("*@" + sender.split("@", 1)[1].lower())
    for e in os.environ.get("EMAIL_ALLOWLIST", "").split(","):
        if e.strip():
            entries.add(e.strip().lower())
    for f in ALLOWLIST_FILES:
        fp = pathlib.Path(f)
        if fp.is_file():
            for line in fp.read_text().splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    entries.add(line.lower())
    return entries


# Check if recipient email matches configured allowlist
def in_scope(email, allow):
    email = email.lower()
    if email in allow:
        return True
    domain = "*@" + email.split("@", 1)[1] if "@" in email else ""
    return domain in allow


# Render Jinja2 template with context
def render(env, template_src, context):
    return env.from_string(template_src).render(**context)


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


# Fetch requesting user email from Microsoft Graph using Object ID
def get_user_email_from_graph(token, object_id):
    url = f"https://graph.microsoft.com/v1.0/users/{object_id}?$select=mail,userPrincipalName,displayName"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            email = data.get("mail") or data.get("userPrincipalName")
            if not email:
                sys.exit(f"Could not determine email for user Object ID {object_id}")
            return email
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        sys.exit(f"Graph user lookup error ({e.code}): {err}")


# Dispatch email message via Microsoft Graph API
def send_via_graph(token, sender_id, to_email, subject, html_body):
    url = f"https://graph.microsoft.com/v1.0/users/{sender_id}/sendMail"
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
        "saveToSentItems": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, None
    except urllib.error.HTTPError as e:
        err = f"HTTP Error {e.code}: {e.read().decode('utf-8')}"
        return False, err
    except Exception as e:
        return False, str(e)


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
    ap.add_argument("--template", required=True, help="path to the HTML (jinja2) template")
    ap.add_argument("--sender", help="optional sender override; validated against requesting user")
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
    ap.add_argument("--transactional", action="store_true", help="bypass allowlist for transactional emails (e.g. RFQs)")
    args = ap.parse_args()

    # Map legacy azure provider to graph
    if args.provider == "azure":
        args.provider = "graph"

    if not args.recipients and not args.to:
        sys.exit("provide --recipients FILE or --to addr [addr ...]")

    graph_token = None
    object_id = None

    # Resolve sender identity from Microsoft Graph API using Entra ID credentials
    if args.provider == "graph":
        tenant_id = get_env("AZURE_TENANT_ID", "ENTRA_TENANT_ID", "DIRECTORY_ID")
        client_id = get_env("AZURE_CLIENT_ID", "ENTRA_CLIENT_ID", "APP_ID")
        client_secret = get_env("AZURE_CLIENT_SECRET", "ENTRA_CLIENT_SECRET", "CLIENT_SECRET")
        object_id = get_env("AZURE_OBJECT_ID", "ENTRA_OBJECT_ID", "OBJECT_ID", "USER_OBJECT_ID")

        if not all([tenant_id, client_id, client_secret, object_id]):
            if args.send or not args.sender:
                sys.exit("Missing Entra ID secrets in environment: requires App ID, Directory ID, Secret, and Object ID")
        else:
            graph_token = get_graph_token(tenant_id, client_id, client_secret)
            resolved_sender = get_user_email_from_graph(graph_token, object_id)

            # Enforce that sending is strictly bound to requesting user
            if args.sender and args.sender.lower() != resolved_sender.lower():
                sys.exit(f"Sender forbidden: Agent is restricted to sending as {resolved_sender}")
            args.sender = resolved_sender
    elif not args.sender:
        sys.exit("--sender required when using non-graph provider")

    recipients = load_recipients(args.recipients, args.to)
    if not recipients:
        sys.exit("no recipients found")
    allow = load_allowlist(args.sender)
    if not allow:
        sys.exit("scope not configured: no sender domain, EMAIL_ALLOWLIST, or allowlist file")

    out_of_scope = [r["email"] for r in recipients if not in_scope(r["email"], allow)]
    if out_of_scope and args.transactional:
        print(f"TRANSACTIONAL MODE: bypassing allowlist for {len(out_of_scope)} recipients.")
        out_of_scope = []

    template_src = pathlib.Path(args.template).read_text()
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

    print(f"sender        : {args.sender}")
    print(f"recipients    : {len(recipients)}")
    print(f"sample subject: {rendered[0]['subject']}")
    print(f"payloads      : {out_dir}/")
    for r in recipients[:5]:
        print(f"  - {r['email']}")
    if len(recipients) > 5:
        print(f"  ... and {len(recipients) - 5} more")
    if out_of_scope:
        print(f"\nOUT OF SCOPE ({len(out_of_scope)}): {', '.join(out_of_scope[:10])}")
        print("These match no allowlist tier. Fix the list or the allowlist before sending.")

    if not args.send:
        print("\nDRY RUN. Nothing sent. Re-run with --send after confirming the above.")
        return 0

    if out_of_scope:
        sys.exit("refusing to send: out-of-scope recipients present (see above)")
    if len(recipients) > BULK_THRESHOLD and not args.confirm_bulk:
        sys.exit(f"{len(recipients)} recipients exceeds {BULK_THRESHOLD}; pass --confirm-bulk")

    archive = pathlib.Path(args.archive_dir)
    archive.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    sent, failed = [], []

    # Dispatch loop for rendered emails
    for r in rendered:
        if args.provider == "graph":
            success, err = send_via_graph(graph_token, object_id, r["email"], r["subject"], r["body"])
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
        "recipient_count": len(recipients),
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
