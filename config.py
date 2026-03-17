import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED = ["EWS_EMAIL", "EWS_PASSWORD", "GMAIL_SENDER", "GMAIL_APP_PASSWORD"]


def print_if_dev(*args, **kwargs):
    """Print only when DEV=true is set in the environment."""
    if os.getenv("DEV", "false").lower() == "true":
        print(*args, **kwargs)


def load():
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in your credentials."
        )

    raw_count = os.getenv("EMAILS_TO_SCAN")

    return {
        # University email (Exchange/OWA)
        "ews_host":        os.getenv("EWS_HOST", "mail.guc.edu.eg"),
        "ews_email":       os.getenv("EWS_EMAIL"),
        "ews_user":        os.getenv("EWS_USER") or os.getenv("EWS_EMAIL"),
        "ews_password":    os.getenv("EWS_PASSWORD"),
        "emails_to_scan":  int(raw_count) if raw_count else None,
        # CMS scraping
        "enable_cms":      os.getenv("ENABLE_CMS", "true").lower() == "true",
        "cms_url":         os.getenv("CMS_URL", "https://cms.guc.edu.eg"),
        "cms_login_url":   os.getenv("CMS_LOGIN_URL", ""),
        "cms_user":        os.getenv("CMS_USER") or os.getenv("EWS_USER") or os.getenv("EWS_EMAIL"),
        "cms_password":    os.getenv("CMS_PASSWORD") or os.getenv("EWS_PASSWORD"),
        # LLM backend — FreeLLM (default) or Ollama
        "use_ollama":      os.getenv("USE_OLLAMA", "false").lower() == "true",
        "use_gemini":      os.getenv("USE_GEMINI", "false").lower() == "true",
        "freellm_key":     os.getenv("FREELLM_KEY", ""),
        "freellm_url":     os.getenv("FREELLM_URL", "https://apifreellm.com/api/v1/chat"),
        "freellm_model":   os.getenv("FREELLM_MODEL", "gpt-4o-mini"),
        "gemini_key":      os.getenv("GEMINI_KEY", ""),
        "gemini_model":    os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "ollama_url":      os.getenv("OLLAMA_URL", "http://localhost:11434"),
        "ollama_model":    os.getenv("OLLAMA_MODEL", "llama3.2"),
        # Gmail notification
        "gmail_sender":    os.getenv("GMAIL_SENDER"),
        "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD"),
        "gmail_recipient": os.getenv("GMAIL_RECIPIENT") or os.getenv("GMAIL_SENDER"),
        # General
        "timezone":        os.getenv("TIMEZONE", "Africa/Cairo"),
        "mark_emails_read": os.getenv("MARK_EMAILS_READ", "false").lower() == "true",
    }
