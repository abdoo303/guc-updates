import json
import re
import time
import requests

import config

try:
    from google import genai as _genai
except ImportError:
    _genai = None

log = config.print_if_dev

# FreeLLM free-tier: 1 request per 30 seconds (extra buffer over the 25s limit)
_FREELLM_INTERVAL   = 30
_FREELLM_429_WAIT   = 60   # seconds to back off after a 429
_freellm_last_call  = 0.0


def _freellm_wait(extra=0):
    global _freellm_last_call
    elapsed = time.time() - _freellm_last_call
    wait    = (_FREELLM_INTERVAL + extra) - elapsed
    if wait > 0:
        log(f"  [rate limit] waiting {wait:.1f}s before next FreeLLM call...")
        time.sleep(wait)
    _freellm_last_call = time.time()


PROMPT_TEMPLATE = """You are a university student assistant. Analyze the email below and extract any events or announcements that a student needs to know about.

Return ONLY a valid JSON object — no explanation, no markdown, no extra text.

Use this exact schema:
{{
  "found": true or false,
  "events": [
    {{
      "title": "clear title e.g. 'Quiz 1' or 'Midterm Exam'",
      "course": "full course name and/or code e.g. 'CSEN 401 - Computer Architecture' or null if not mentioned",
      "instructor": "name of the instructor or sender if identifiable, or null",
      "type": "quiz | midterm | final | test | assignment | presentation | cancellation | holiday | deadline | announcement | other",
      "date": "YYYY-MM-DD or null if not mentioned",
      "time": "HH:MM in 24-hour format or null if not mentioned",
      "duration_hours": number or null,
      "location": "room number, building, or 'online' or null",
      "topics": "material covered e.g. 'Lectures 1-3, Chapter 5' or null",
      "description": "1-2 sentence summary"
    }}
  ]
}}

INCLUDE events about:
- Exams: quizzes, midterms, finals, tests
- Assignments or project deadlines
- Cancelled tutorials, lectures, or classes (type: cancellation)
- University holidays or no-class days (type: holiday)
- Academic deadlines: registration, withdrawal, grade submission (type: deadline)
- Important academic announcements: schedule changes, room changes, makeup sessions (type: announcement)

IGNORE and do NOT include:
- Social events, concerts, fairs, festivals
- Sports events or competitions
- Bus or transportation schedules
- Recreational or extracurricular activities
- Generic newsletters or promotional content

If nothing relevant is found, return {{"found": false, "events": []}}.

--- EMAIL START ---
Subject: {subject}
From: {sender}
Date: {date}

{body}
--- EMAIL END ---"""


def _extract_json(text):
    """Try to extract a JSON object from potentially noisy LLM output."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _call_freellm(prompt, cfg):
    """Call the apifreellm.com API."""
    url = cfg["freellm_url"].rstrip("/")
    headers = {
        "Authorization": f"Bearer {cfg['freellm_key']}",
        "Content-Type": "application/json",
    }
    payload = {"message": prompt}

    _freellm_wait()
    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            raw = (
                data.get("response")
                or data.get("message")
                or data.get("content")
                or data.get("text")
                or data.get("answer")
                or ""
            )
            if not raw and isinstance(data, str):
                raw = data
            result = _extract_json(str(raw))
            if result and "found" in result:
                return result
            if attempt == 0:
                log(f"  [warn] Could not parse FreeLLM response, retrying... (got: {str(raw)[:100]})")
        except requests.exceptions.ConnectionError:
            raise SystemExit(f"Cannot connect to FreeLLM at {url}.")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                global _freellm_last_call
                retry_after = int(e.response.headers.get("Retry-After", _FREELLM_429_WAIT))
                log(f"  [rate limit] 429 received — waiting {retry_after}s then retrying...")
                time.sleep(retry_after)
                _freellm_last_call = time.time()
            else:
                raise SystemExit(f"FreeLLM API error: {e}\nCheck FREELLM_KEY in your .env.")
        except requests.exceptions.Timeout:
            log(f"  [warn] FreeLLM timed out on attempt {attempt + 1}")
    return None


def _call_gemini(prompt, cfg):
    """Call the Google Gemini API (free tier via Google AI Studio key)."""
    if _genai is None:
        raise SystemExit(
            "google-genai package not installed.\n"
            "Run: pip install google-genai"
        )
    client = _genai.Client(api_key=cfg["gemini_key"])
    for attempt in range(2):
        try:
            resp = client.models.generate_content(
                model=cfg["gemini_model"],
                contents=prompt,
            )
            result = _extract_json(resp.text)
            if result and "found" in result:
                return result
            if attempt == 0:
                log(f"  [warn] Could not parse Gemini response, retrying... (got: {resp.text[:100]})")
        except Exception as e:
            if attempt == 0:
                log(f"  [warn] Gemini error: {e}, retrying...")
            else:
                log(f"  [error] Gemini failed: {e}")
    return None


def _call_ollama(prompt, cfg):
    """Call the local Ollama instance."""
    url = f"{cfg['ollama_url']}/api/generate"
    payload = {
        "model": cfg["ollama_model"],
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            result = _extract_json(raw)
            if result and "found" in result:
                return result
            if attempt == 0:
                log("  [warn] Could not parse Ollama response, retrying...")
        except requests.exceptions.ConnectionError:
            raise SystemExit(
                f"Cannot connect to Ollama at {cfg['ollama_url']}.\n"
                "Make sure Ollama is running: `ollama serve`"
            )
        except requests.exceptions.Timeout:
            log(f"  [warn] Ollama timed out on attempt {attempt + 1}")
    return None


def parse_email(email_data, cfg):
    """
    Parse email/document content via the configured LLM backend.
      USE_OLLAMA=true  → local Ollama
      USE_GEMINI=true  → Google Gemini (free API key)
      default          → FreeLLM
    Returns a dict with 'found' and 'events', or None on failure.
    """
    prompt = PROMPT_TEMPLATE.format(
        subject=email_data["subject"],
        sender=email_data["sender"],
        date=email_data["date"],
        body=email_data["body"][:4000],
    )

    if cfg.get("use_ollama"):
        return _call_ollama(prompt, cfg)
    if cfg.get("use_gemini"):
        return _call_gemini(prompt, cfg)
    return _call_freellm(prompt, cfg)
