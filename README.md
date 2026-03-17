# GUC Parser

Scans your GUC university inbox and CMS, extracts academic events using an LLM, and emails you a summary with a `.ics` calendar attachment once per day.

---

## Prerequisites

-   Python 3.10+
-   A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) enabled
-   Your GUC email credentials (Exchange/OWA)
-   One LLM backend (see [LLM Backends](#llm-backends))

---

## Setup

### 1. Clone & create a virtual environment

```bash
git clone https://github.com/abdoo303/guc-updates.git
cd guc-parser
python3 -m venv .venv
```

Activate the environment:

| Platform             | Command                      |
| -------------------- | ---------------------------- |
| macOS / Linux        | `source .venv/bin/activate`  |
| Windows (cmd)        | `.venv\Scripts\activate.bat` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
# University email (Exchange)
EWS_EMAIL=your.name@guc.edu.eg
EWS_PASSWORD=your_password

# Gmail notification
GMAIL_SENDER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # 16-char App Password
GMAIL_RECIPIENT=you@gmail.com            # defaults to GMAIL_SENDER if blank

# How many recent emails to scan
EMAILS_TO_SCAN=50
```

All other values have sensible defaults. See `.env.example` for the full reference.

---

## LLM Backends

Pick **one** backend. Set the corresponding flag in `.env`.

### FreeLLM (default — no setup needed)

Leave both flags false. Get a free key at [apifreellm.com](https://apifreellm.com) and set:

```env
FREELLM_KEY=your_key_here
```

> Free tier: 1 request per 25 seconds. the best option if you don't have a credit card to provide to gemini and don't want to pull ollama.

### Gemini (free option but requires a credit card to activate the key)

Get a free key from [Google AI Studio](https://aistudio.google.com), then set:

```env
USE_GEMINI=true
GEMINI_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash   # default
```

### Ollama (local, no internet required, most secure)

Install [Ollama](https://ollama.com), pull a model, then set:

```bash
ollama pull llama3.2
```

```env
USE_OLLAMA=true
OLLAMA_MODEL=llama3.2
```

---

## Running manually

```bash
# Normal run
python main.py

# Preview only — no email sent
python main.py --dry-run

# Scan only the 20 most recent emails
python main.py --count 20
```

---

## Auto-run on login (once per day)

### macOS — launchd

1. Copy the plist to LaunchAgents:

```bash
cp com.guc.emailparser.plist ~/Library/LaunchAgents/
```

2. Edit the plist and make sure the path matches your project location:

```xml
<string>/Users/YOUR_USERNAME/projects/guc-parser/run.sh</string>
```

3. Load the agent:

```bash
launchctl load ~/Library/LaunchAgents/com.guc.emailparser.plist
```

The script runs at login and every hour after that. It skips if it already ran today.

**Logs:** `~/Library/Logs/guc-parser.log`

To unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.guc.emailparser.plist
```

---

### Linux — cron

Make `run.sh` executable and add a cron job:

```bash
chmod +x run.sh
crontab -e
```

Add this line to run every hour (the script skips if already ran today):

```
0 * * * * /home/YOUR_USERNAME/projects/guc-parser/run.sh >> /home/YOUR_USERNAME/logs/guc-parser.log 2>&1
```

Make sure `run.sh` points to the correct Python path. Update the `DIR` variable at the top of `run.sh` if needed:

```bash
DIR=/home/YOUR_USERNAME/projects/guc-parser
PYTHON="$DIR/.venv/bin/python3"
```

---

### Windows — Task Scheduler

1. Create a batch file `run.bat` in the project folder:

```bat
@echo off
cd /d C:\Users\YOUR_USERNAME\projects\guc-parser
.venv\Scripts\python.exe main.py
```

2. Open **Task Scheduler** → **Create Basic Task**:

    - **Trigger:** At log on
    - **Action:** Start a program → browse to `run.bat`
    - **Repeat task every:** 1 hour (under Advanced settings)

3. To prevent duplicate runs on the same day, add a check at the top of `run.bat`:

```bat
@echo off
cd /d C:\Users\YOUR_USERNAME\projects\guc-parser
for /f %%i in ('.venv\Scripts\python.exe -c "import json,os; d=json.load(open(\"json/last_run.json\")); print(d.get(\"date\",\"\"))"') do set LAST=%%i
for /f %%i in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
if "%LAST%"=="%TODAY%" exit /b 0
.venv\Scripts\python.exe main.py
```

**Logs:** Redirect output in Task Scheduler under **Edit Action → Add arguments**:

```
>> C:\Users\YOUR_USERNAME\logs\guc-parser.log 2>&1
```

---

## Gmail App Password setup

1. Go to your Google Account → **Security** → **2-Step Verification** (must be enabled)
2. Search for **App passwords**
3. Create a new app password → copy the 16-character key
4. Paste it into `GMAIL_APP_PASSWORD` in your `.env`
