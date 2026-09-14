#!/usr/bin/env python3
"""Render, scope-check, dry-run, send, and archive an email campaign via ACS.

Default mode is a dry run: it renders payloads and prints a summary but never
calls `az`. Pass --send to actually dispatch. See references/recipients.md for
the recipients file format, allowlist syntax, and manifest fields.

Examples:
  # dry run (default): render + summarize, no send
  python send_campaign.py --template alert.html.j2 --recipients recipients.csv \
    --sender no-reply@yourdomain.com --subject "Security notice"

  # real send (per-recipient personalization, archived + manifested)
  python send_campaign.py --template alert.html.j2 --recipients recipients.csv \
    --sender no-reply@yourdomain.com --subject "Security notice" \
    --scenario password-reset --authorizer jane@yourdomain.com --send
"""
import argparse, csv, hashlib, json, os, pathlib, subprocess, sys, time
import urllib.request, urllib.error

try:
    from jinja2 import Environment, select_autoescape
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

BULK_THRESHOLD = 50
ALLOWLIST_FILES = ["/workspace/email_allowlist.txt",
                   "plugins/email-automation/allowlist.txt"]


def load_recipients(path, inline):
    """Return a list of dicts, each with at least an 'email' key."""
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


def load_allowlist(sender):
    """Resolve scope: sender domain, EMAIL_ALLOWLIST env, then gitignored files."""
    entries = set()
    if "@" in sender:
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


def in_scope(email, allow):
    email = email.lower()
    if email in allow:
        return True
    domain = "*@" + email.split("@", 1)[1] if "@" in email else ""
    return domain in allow


def render(env, template_src, context):
    return env.from_string(template_src).render(**context)


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
        with urllib.request.urlopen(req) as response:
            return True, None
    except urllib.error.HTTPError as e:
        error_msg = f"HTTP Error {e.code}: {e.read().decode('utf-8')}"
        return False, error_msg
    except Exception as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser(description="Render/send an ACS email campaign.")
    ap.add_argument("--template", required=True, help="path to the HTML (jinja2) template")
    ap.add_argument("--sender", required=True, help="owned, ACS-verified sender address")
    ap.add_argument("--subject", required=True, help="subject line (may use jinja2 vars)")
    ap.add_argument("--recipients", help="recipients CSV or JSON file")
    ap.add_argument("--to", nargs="*", help="inline recipient addresses (small sends)")
    ap.add_argument("--scenario", default="", help="scenario label for the manifest")
    ap.add_argument("--authorizer", default="", help="who approved this (simulations)")
    ap.add_argument("--connection-string", default="", help="ACS connection string")
    ap.add_argument("--archive-dir", default="/workspace/email_archive")
    ap.add_argument("--preview-dir", default="/workspace/email_preview")
    ap.add_argument("--send", action="store_true", help="actually send (default: dry run)")
    ap.add_argument("--confirm-bulk", action="store_true", help="ack a >%d send" % BULK_THRESHOLD)
    ap.add_argument("--provider", choices=["azure", "brevo"], default="azure", help="email provider (default: azure)")
    ap.add_argument("--transactional", action="store_true", help="bypass allowlist for transactional emails (e.g. RFQs)")
    args = ap.parse_args()

    if not args.recipients and not args.to:
        sys.exit("provide --recipients FILE or --to addr [addr ...]")

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

    # Render every payload up front (used by both dry run and send).
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

    print(f"sender       : {args.sender}")
    print(f"recipients   : {len(recipients)}")
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

    # ---- send path ----
    if out_of_scope:
        sys.exit("refusing to send: out-of-scope recipients present (see above)")
    if len(recipients) > BULK_THRESHOLD and not args.confirm_bulk:
        sys.exit(f"{len(recipients)} recipients exceeds {BULK_THRESHOLD}; pass --confirm-bulk")
        
    if args.provider == "azure" and not args.connection_string and not os.environ.get("AZURE_COMMUNICATION_CONNECTION_STRING"):
        sys.exit("no auth: set AZURE_COMMUNICATION_CONNECTION_STRING or pass --connection-string")
    if args.provider == "brevo" and not os.environ.get("BREVO_API_KEY"):
        sys.exit("no auth: set BREVO_API_KEY environment variable for Brevo provider")

    archive = pathlib.Path(args.archive_dir)
    archive.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    sent, failed = [], []
    for r in rendered:
        if args.provider == "azure":
            cmd = ["az", "communication", "email", "send",
                   "--sender", args.sender, "--to", r["email"],
                   "--subject", r["subject"], "--html", r["body"]]
            if args.connection_string:
                cmd += ["--connection-string", args.connection_string]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                sent.append(r["email"])
                (archive / f"{ts}_{r['email'].replace('/', '_')}.html").write_text(r["body"])
            else:
                # Never silently retry: record the exact error and keep going.
                failed.append({"email": r["email"], "error": res.stderr.strip()})
        elif args.provider == "brevo":
            api_key = os.environ.get("BREVO_API_KEY")
            success, err = send_via_brevo(api_key, args.sender, r["email"], r["subject"], r["body"])
            if success:
                sent.append(r["email"])
                (archive / f"{ts}_{r['email'].replace('/', '_')}.html").write_text(r["body"])
            else:
                failed.append({"email": r["email"], "error": err})

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
