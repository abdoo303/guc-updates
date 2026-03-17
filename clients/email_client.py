"""
Email fetching via Exchange Web Services (EWS) using exchangelib.
Works with on-premise Microsoft Exchange (OWA) — no Graph API, no IMAP needed.
"""
from bs4 import BeautifulSoup
from exchangelib import Credentials, Account, DELEGATE, Configuration
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
import urllib3

# Suppress SSL warnings for university servers that use self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter


def _strip_html(html):
    return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()


def fetch_emails(cfg):
    """
    Connect to Exchange via EWS and return the most recent N emails.
    Returns list of dicts: { subject, sender, date, body }
    """
    ews_url = f"https://{cfg['ews_host']}/EWS/Exchange.asmx"

    credentials = Credentials(
        username=cfg["ews_user"],
        password=cfg["ews_password"],
    )

    ews_config = Configuration(
        service_endpoint=ews_url,
        credentials=credentials,
    )

    account = Account(
        primary_smtp_address=cfg["ews_email"],
        config=ews_config,
        autodiscover=False,
        access_type=DELEGATE,
    )

    emails = []
    n = cfg.get("emails_to_scan")
    mark_read = cfg.get("mark_emails_read", False)
    qs = account.inbox.filter(is_read=False).order_by("-datetime_received")
    inbox = qs[:n] if n else qs  # None = all unread

    for msg in inbox:
        body_text = ""
        if msg.body:
            content = str(msg.body)
            if msg.body.body_type == "HTML":
                body_text = _strip_html(content)
            else:
                body_text = content.strip()

        sender = ""
        if msg.sender:
            sender = msg.sender.email_address or msg.sender.name or ""

        if mark_read:
            msg.is_read = True
            msg.save(update_fields=["is_read"])

        emails.append({
            "subject": msg.subject or "(no subject)",
            "sender": sender,
            "date": str(msg.datetime_received) if msg.datetime_received else "",
            "body": body_text,
        })

    return emails
