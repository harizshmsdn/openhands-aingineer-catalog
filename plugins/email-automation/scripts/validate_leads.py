#!/usr/bin/env python3
"""
Validates a CSV of leads to ensure emails have proper syntax and valid MX records.
Filters out invalid emails to prevent hard bounces.

Usage:
  python validate_leads.py --input leads.csv --output leads_validated.csv
"""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

# Standard email regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def check_syntax(email):
    return bool(EMAIL_REGEX.match(email))

def check_mx(domain):
    try:
        # Query MX records via dig
        res = subprocess.run(["dig", "+short", "MX", domain], capture_output=True, text=True, timeout=5)
        return bool(res.stdout.strip())
    except Exception as e:
        print(f"  [!] MX lookup failed for {domain}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Validate email syntax and MX records in a CSV.")
    parser.add_argument("--input", required=True, help="Input CSV file containing an 'email' column")
    parser.add_argument("--output", required=True, help="Output CSV file for validated leads")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        sys.exit(f"Input file not found: {args.input}")

    with open(input_path, mode="r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        if "email" not in fieldnames:
            sys.exit("Error: Input CSV must contain an 'email' column.")
        
        rows = list(reader)

    valid_rows = []
    invalid_rows = []
    
    for row in rows:
        email = row.get("email", "").strip()
        if not email:
            invalid_rows.append((row, "Empty email"))
            continue

        if not check_syntax(email):
            invalid_rows.append((row, "Syntax error"))
            continue

        domain = email.split("@")[1]
        if not check_mx(domain):
            invalid_rows.append((row, "No MX record"))
            continue

        valid_rows.append(row)

    with open(args.output, mode="w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(valid_rows)

    print(f"Validated {len(rows)} leads: {len(valid_rows)} valid, {len(invalid_rows)} dropped -> {args.output}")

if __name__ == "__main__":
    main()
