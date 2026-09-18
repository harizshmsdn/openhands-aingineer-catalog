#!/usr/bin/env python3
import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("httpx is required. pip install httpx")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

# Strict email regex excluding image extensions and bad domains
EMAIL_REGEX = re.compile(
    r"\b(?![^@\s]+@[^@\s]+\.(?:png|jpg|jpeg|gif|webp|svg|woff|woff2|ico|js|css)\b)"
    r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b"
)
BAD_DOMAINS = ["sentry.io", "w3.org", "example.com", "sentry-trace.com"]

def clean_emails(emails):
    cleaned = set()
    for e in emails:
        e = e.lower()
        domain = e.split("@")[1] if "@" in e else ""
        if domain not in BAD_DOMAINS and not e.startswith("no-reply"):
            cleaned.add(e)
    return list(cleaned)

def extract_from_html(html):
    emails = EMAIL_REGEX.findall(html)
    return clean_emails(emails)

def fetch_httpx(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
        if r.status_code == 200:
            return r.text
        return None
    except Exception:
        return None

def fetch_playwright(url):
    if not sync_playwright:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            content = page.content()
            browser.close()
            return content
    except Exception:
        return None

def step_2a(domain):
    paths = ["", "/contact", "/about", "/contact-us"]
    found_emails = set()
    for path in paths:
        url = f"https://{domain}{path}"
        html = fetch_httpx(url)
        if html:
            found_emails.update(extract_from_html(html))
        else:
            # Fallback to Playwright if httpx failed or was blocked
            html = fetch_playwright(url)
            if html:
                found_emails.update(extract_from_html(html))
        if found_emails:
            break # Stop if we found emails on this domain
    return list(found_emails)

def step_2b(domain):
    # Run theHarvester
    try:
        res = subprocess.run(
            ["theHarvester", "-d", domain, "-b", "all"],
            capture_output=True, text=True, timeout=60
        )
        emails = EMAIL_REGEX.findall(res.stdout)
        return clean_emails(emails)
    except Exception as e:
        print(f"theHarvester failed for {domain}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input CSV with 'domain' column")
    parser.add_argument("--output", required=True, help="Output CSV with 'email' and 'notes'")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "domain" not in reader.fieldnames:
            sys.exit("Input must contain a 'domain' column.")
        rows = list(reader)

    out_fieldnames = reader.fieldnames + ["email", "notes"] if "email" not in reader.fieldnames else reader.fieldnames
    if "notes" not in out_fieldnames:
        out_fieldnames.append("notes")

    out_rows = []
    for row in rows:
        domain = row["domain"].strip()
        if not domain:
            continue

        # Extract emails via scraping or Harvester
        emails = step_2a(domain) or step_2b(domain)
        row["notes"] = ""
        if emails:
            row["email"] = emails[0]
        else:
            row["email"] = ""
            row["notes"] = "Form only - manual submission required"

        out_rows.append(row)

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    found_count = sum(1 for r in out_rows if r["email"])
    print(f"Extracted {found_count} email(s) from {len(out_rows)} domains -> {args.output}")

if __name__ == "__main__":
    main()
