"""
Diagnostic test for the FreeLLM API connection.
Run with: python tests/test-freellm.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
import config

cfg = config.load()

key   = cfg["freellm_key"]
url   = cfg["freellm_url"].rstrip("/")
model = cfg["freellm_model"]

print(f"FreeLLM URL:   {url}")
print(f"FreeLLM Model: {model}")
print(f"API Key:       {key[:8]}{'*' * (len(key) - 8) if len(key) > 8 else '(too short)'}")
print()

SAMPLE = {
    "subject": "Quiz 1 Allocation",
    "sender":  "dr.test@guc.edu.eg",
    "date":    "2026-03-15",
    "body":    "Quiz 1 will take place on Sunday March 22nd at 10:00 AM in Hall A. It covers Lectures 1-4.",
}

PROMPT = (
    "You are a university student assistant. Extract academic events from this email.\n"
    "Return ONLY valid JSON: {\"found\": true/false, \"events\": [...]}\n\n"
    f"Subject: {SAMPLE['subject']}\nFrom: {SAMPLE['sender']}\n\n{SAMPLE['body']}"
)

headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type":  "application/json",
}

payload = {"message": PROMPT}

print(f"POST {url}")
print("-" * 60)

try:
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    print(f"Status: {resp.status_code}")
    print(f"Response:\n{resp.text[:1000]}")
except requests.exceptions.ConnectionError as e:
    print(f"Connection error: {e}")
    print("\nCheck FREELLM_URL in your .env.")
except requests.exceptions.Timeout:
    print("Request timed out after 30s.")
