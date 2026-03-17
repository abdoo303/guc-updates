"""
Diagnostic test for the Gemini API connection.
Run with: python tests/test-gemini.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from google import genai

cfg    = config.load()
key    = cfg["gemini_key"]
model  = cfg["gemini_model"]

print(f"Gemini Model: {model}")
print(f"API Key:      {key[:8]}{'*' * (len(key) - 8) if len(key) > 8 else '(too short)'}")
print("-" * 60)

client   = genai.Client(api_key=key)
response = client.models.generate_content(
    model=model,
    contents="Say hello and confirm you are working.",
)
print(response.text)
