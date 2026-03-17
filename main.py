#!/usr/bin/env python3
"""
University Email -> Ollama -> Gmail Notification
Scans your university inbox, extracts academic events, and emails you a
summary with a .ics attachment so you can add them to your calendar in one tap.

Usage:
    python main.py              # scan and send email if new events found
    python main.py --dry-run    # preview only, no email sent
    python main.py --count 20   # scan only the 20 most recent unread emails
"""
import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import config
import clients.email_client as email_client
import clients.cms_client as cms_client
import clients.llm_client as llm_client
import clients.notifier as notifier

SEEN_STORE = "json/seen_before.json"

log = config.print_if_dev


def _email_hash(mail):
    """Hash the full email text so the same email is never processed twice."""
    raw = f"{mail['subject']}|{mail['sender']}|{mail['body']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_seen(path):
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()


def _save_seen(seen, path):
    with open(path, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview events without sending email.")
    parser.add_argument("--count", type=int, default=None,
                        help="Number of recent emails to scan. Omit to use EMAILS_TO_SCAN env var.")
    args = parser.parse_args()

    log("Loading config...")
    cfg = config.load()

    # CLI --count overrides the EMAILS_TO_SCAN env var
    if args.count is not None:
        cfg["emails_to_scan"] = args.count

    label = f"last {cfg['emails_to_scan']}" if cfg["emails_to_scan"] else "all unread"
    log(f"Fetching {label} emails" + (" and CMS data" if cfg["enable_cms"] else "") + "...")

    emails        = []
    cms_docs_raw  = []
    course_map    = {}
    content_items = []
    cms_error     = None

    if cfg["enable_cms"]:
        with ThreadPoolExecutor(max_workers=2) as pool:
            email_fut = pool.submit(email_client.fetch_emails, cfg)
            cms_fut   = pool.submit(cms_client.fetch_cms_data, cfg)

            emails = email_fut.result()
            log(f"Fetched {len(emails)} email(s).")

            try:
                cms_docs_raw, course_map, content_items = cms_fut.result()
                log(f"Fetched {len(cms_docs_raw)} CMS announcement(s), "
                    f"{len(content_items)} content item(s).")
            except Exception as e:
                cms_error = e
                print(f"CMS fetch failed: {e}")
    else:
        emails = email_client.fetch_emails(cfg)
        log(f"Fetched {len(emails)} email(s).")

    seen     = _load_seen(SEEN_STORE)
    new_seen = set()
    all_events = []

    # ── Email scan ────────────────────────────────────────────────────────────
    log("\n" + "=" * 60)
    for i, mail in enumerate(emails, 1):
        subject = mail["subject"]
        h = _email_hash(mail)

        if h in seen:
            log(f"[{i}/{len(emails)}] (already seen) {subject[:60]} — stopping scan.")
            break

        log(f"[{i}/{len(emails)}] {subject[:70]}")
        new_seen.add(h)

        result = llm_client.parse_email(mail, cfg)

        if result is None:
            log("  -> Parse failed, skipping.\n")
            continue

        if not result.get("found") or not result.get("events"):
            log("  -> Nothing relevant.\n")
            continue

        events = result["events"]
        log(f"  -> {len(events)} event(s) found:")
        for ev in events:
            log(f"     [{ev.get('type','?')}] {ev.get('title')} | {ev.get('date','no date')}")
        all_events.extend(events)
        log()

    log("=" * 60)
    skipped = len(emails) - len(new_seen)
    log(f"Email scan: {len(emails)} fetched, {skipped} already seen, {len(all_events)} events found.")

    # ── CMS parse ─────────────────────────────────────────────────────────────
    new_content = []
    if cfg["enable_cms"]:
        log("\n" + "=" * 60)
        if cms_error:
            print(f"CMS scraping skipped: {cms_error}")
        else:
            for doc in cms_docs_raw:
                h = cms_client.content_hash(doc)
                if h in seen:
                    log(f"  (already seen) {doc['subject'][:60]}")
                    continue

                log(f"  Parsing: {doc['subject'][:70]}")
                new_seen.add(h)

                result = llm_client.parse_email(doc, cfg)
                if not result or not result.get("found") or not result.get("events"):
                    log("  -> Nothing relevant.\n")
                    continue

                events = result["events"]
                log(f"  -> {len(events)} event(s) found:")
                for ev in events:
                    log(f"     [{ev.get('type','?')}] {ev.get('title')} | {ev.get('date','no date')}")
                all_events.extend(events)
                log()

            for item in content_items:
                h = cms_client.content_item_hash(item)
                if h in seen:
                    continue
                new_seen.add(h)
                new_content.append(item)

            log(f"CMS parse: {len(cms_docs_raw)} announcements, {len(new_content)} new content item(s).")

    # ── Apply course map ───────────────────────────────────────────────────────
    if course_map:
        all_events = notifier.apply_course_map(all_events, course_map)
        log(f"Course map applied ({len(course_map)} course(s)).")

    # ── Send ──────────────────────────────────────────────────────────────────
    log("=" * 60)
    if not all_events and not new_content:
        if args.dry_run:
            log("Dry run — nothing new found.")
            return
        notifier.send_nothing_new(cfg)
        print(f"Nothing new — notification sent to {cfg['gmail_recipient']}.")
        seen.update(new_seen)
        _save_seen(seen, SEEN_STORE)
        return

    if args.dry_run:
        log(f"Dry run — would send email with {len(all_events)} event(s) and {len(new_content)} content item(s).")
        return

    notifier.send_events(all_events, cfg, new_content=new_content)
    print(f"Email sent: {len(all_events)} event(s), {len(new_content)} content item(s) to {cfg['gmail_recipient']}.")

    seen.update(new_seen)
    _save_seen(seen, SEEN_STORE)


if __name__ == "__main__":
    main()
