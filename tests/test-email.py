"""
Test script — sends a notification email with 3 fake quiz events.
Bypasses IMAP and Ollama completely.
Run with: python test.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import clients.notifier as notifier

FAKE_EVENTS = [
    {
        "title":          "Quiz 1 - Compilers",
        "type":           "quiz",
        "date":           "2026-03-18",
        "time":           "10:00",
        "duration_hours": 1,
        "location":       "Hall A",
        "topics":         "Lecture 1 & 2 - Lexical Analysis",
        "description":    "First quiz covering the first two lectures.",
    },
    {
        "title":          "Quiz 2 - Operating Systems",
        "type":           "quiz",
        "date":           "2026-03-19",
        "time":           "12:00",
        "duration_hours": 1,
        "location":       "Hall B",
        "topics":         "Chapter 3 - Process Scheduling",
        "description":    "Second quiz on process scheduling algorithms.",
    },
    {
        "title":          "Quiz 3 - Networks",
        "type":           "quiz",
        "date":           "2026-03-20",
        "time":           "14:00",
        "duration_hours": 1,
        "location":       "Online",
        "topics":         "Lecture 4 - TCP/IP",
        "description":    "Third quiz covering TCP/IP fundamentals.",
    },
]

cfg = config.load()
notifier.send_events(FAKE_EVENTS, cfg)
print(f"Test email sent to {cfg['gmail_recipient']}.")
