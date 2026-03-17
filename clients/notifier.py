"""
Sends event summary emails via Gmail SMTP with an .ics calendar attachment.
No Google Cloud needed — just a Gmail account + App Password.
Tap the .ics on your phone to add all events to your calendar at once.
Deduplication is handled upstream in main.py via email-content hashing.
"""
import datetime
import re
import smtplib
import urllib.parse
import uuid
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event as ICalEvent

TYPE_LABELS = {
    "quiz":         "Quiz",
    "midterm":      "Midterm Exam",
    "final":        "Final Exam",
    "test":         "Test",
    "assignment":   "Assignment Due",
    "presentation": "Presentation",
    "cancellation": "Cancelled",
    "holiday":      "Holiday / No Class",
    "deadline":     "University Deadline",
    "announcement": "Announcement",
    "other":        "Event",
}

# Event types that belong in the calendar (have a concrete date/deadline)
SCHEDULED_TYPES = {"quiz", "midterm", "final", "test", "assignment", "presentation", "deadline"}


def _is_scheduled(ev):
    return ev.get("type") in SCHEDULED_TYPES and ev.get("date") not in (None, "", "null")


def apply_course_map(events, course_map):
    """
    Replace course codes with full names in every text field of each event.
    Handles all variants: CSEN1002, CSEN 1002, csen1002, csen 1002, etc.
    """
    patterns = []
    for code, name in course_map.items():
        m = re.match(r'^([A-Za-z]+)(\d+)$', code)
        if m:
            pat = re.compile(r'\b' + m.group(1) + r'\s*' + m.group(2) + r'\b', re.IGNORECASE)
            patterns.append((pat, name))

    def _replace(text):
        if not text or str(text) in ("null", "None"):
            return text
        for pat, name in patterns:
            text = pat.sub(name, str(text))
        return text

    for ev in events:
        for field in ("title", "course", "description", "topics", "instructor"):
            if ev.get(field):
                ev[field] = _replace(ev[field])

    return events


def _build_ics(events, timezone):
    tz = ZoneInfo(timezone)
    cal = Calendar()
    cal.add("prodid", "-//GUC Email Parser//EN")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")

    for ev in events:
        date_str = ev.get("date")
        if not date_str:
            continue

        ie = ICalEvent()
        ie.add("uid", str(uuid.uuid4()))
        ie.add("dtstamp", datetime.datetime.now(datetime.timezone.utc))
        ie.add("summary", ev.get("title", "Event"))

        desc_parts = []
        if ev.get("type"):
            desc_parts.append(f"Type: {TYPE_LABELS.get(ev['type'], ev['type'])}")
        if ev.get("topics") and ev.get("topics") not in (None, "null"):
            desc_parts.append(f"Topics: {ev['topics']}")
        if ev.get("description"):
            desc_parts.append(ev["description"])
        ie.add("description", "\n".join(desc_parts))

        if ev.get("location") and ev.get("location") not in (None, "null"):
            ie.add("location", ev["location"])

        time_str = ev.get("time")
        duration = ev.get("duration_hours") or 1
        try:
            if time_str and str(time_str) not in ("null", "None", ""):
                start_dt = datetime.datetime.strptime(
                    f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=tz)
                end_dt = start_dt + datetime.timedelta(hours=float(duration))
                ie.add("dtstart", start_dt)
                ie.add("dtend", end_dt)
            else:
                d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                ie.add("dtstart", d)
                ie.add("dtend", d + datetime.timedelta(days=1))
        except (ValueError, TypeError):
            continue

        cal.add_component(ie)

    return cal.to_ical()


def _gcal_link(ev, timezone):
    """Build a one-click Google Calendar 'add event' URL."""
    date_str = ev.get("date", "")
    time_str = ev.get("time")
    duration = ev.get("duration_hours") or 1

    try:
        if time_str and str(time_str) not in ("null", "None", ""):
            start = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            end   = start + datetime.timedelta(hours=float(duration))
            dates = f"{start.strftime('%Y%m%dT%H%M%S')}/{end.strftime('%Y%m%dT%H%M%S')}"
        else:
            d     = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            dates = f"{d.strftime('%Y%m%d')}/{(d + datetime.timedelta(days=1)).strftime('%Y%m%d')}"
    except (ValueError, TypeError):
        return None

    desc_parts = []
    if ev.get("course") and str(ev["course"]) not in ("null", "None"):
        desc_parts.append(f"Course: {ev['course']}")
    if ev.get("instructor") and str(ev["instructor"]) not in ("null", "None"):
        desc_parts.append(f"Instructor: {ev['instructor']}")
    if ev.get("topics") and str(ev["topics"]) not in ("null", "None"):
        desc_parts.append(f"Topics: {ev['topics']}")
    if ev.get("description"):
        desc_parts.append(ev["description"])

    params = {
        "text":     ev.get("title", "Event"),
        "dates":    dates,
        "ctz":      timezone,
        "details":  "\n".join(desc_parts),
        "location": ev.get("location") or "",
    }
    return "https://calendar.google.com/calendar/r/eventedit?" + urllib.parse.urlencode(params)


# Badge background / text colours per event type
_BADGE = {
    "quiz":         ("#e8f0fe", "#1557b0"),
    "midterm":      ("#fce8e6", "#b31412"),
    "final":        ("#b31412", "#ffffff"),
    "test":         ("#fce8e6", "#b31412"),
    "assignment":   ("#e6f4ea", "#0d652d"),
    "presentation": ("#fef7e0", "#7a4f00"),
    "cancellation": ("#f1f3f4", "#3c4043"),
    "holiday":      ("#e6f4ea", "#0d652d"),
    "deadline":     ("#fce8e6", "#b31412"),
    "announcement": ("#e8f0fe", "#1557b0"),
    "other":        ("#f1f3f4", "#3c4043"),
}


def _badge(ev_type):
    bg, fg = _BADGE.get(ev_type, ("#f1f3f4", "#3c4043"))
    label  = TYPE_LABELS.get(ev_type, "Event")
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f'font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;'
        f'padding:3px 8px;border-radius:12px;margin-bottom:6px">{label}</span>'
    )


def _event_card(ev, timezone, show_btn, border_color):
    """Render one event as a styled card div."""
    link = _gcal_link(ev, timezone) if show_btn else None

    def val(v):
        return v and str(v) not in ("null", "None", "", "none")

    # Meta line
    meta_parts = []
    if val(ev.get("date")):
        meta_parts.append(f'<b>{ev["date"]}</b>')
    if val(ev.get("time")):
        meta_parts.append(ev["time"])
    if val(ev.get("duration_hours")):
        meta_parts.append(f'{ev["duration_hours"]}h')
    meta_line = (
        f'<div style="font-size:12px;color:#5f6368;margin-bottom:6px">'
        + ' &nbsp;&#183;&nbsp; '.join(meta_parts) +
        '</div>'
    ) if meta_parts else ""

    # Detail rows
    details = ""
    if val(ev.get("course")):
        details += (
            f'<div style="font-size:13px;color:#1a73e8;font-weight:600;margin-bottom:2px">'
            f'{ev["course"]}</div>'
        )
    if val(ev.get("instructor")):
        details += f'<div style="font-size:12px;color:#5f6368;margin-bottom:2px">Instructor: {ev["instructor"]}</div>'
    if val(ev.get("location")):
        details += f'<div style="font-size:12px;color:#5f6368;margin-bottom:2px">Location: {ev["location"]}</div>'
    if val(ev.get("topics")):
        details += f'<div style="font-size:12px;color:#5f6368;margin-bottom:2px">Topics: {ev["topics"]}</div>'
    if val(ev.get("description")):
        details += (
            f'<div style="font-size:12px;color:#80868b;margin-top:4px;'
            f'font-style:italic">{ev["description"]}</div>'
        )

    btn = ""
    if link:
        btn = (
            f'<div style="margin-top:12px">'
            f'<a href="{link}" style="display:inline-block;background:#1a73e8;color:#ffffff;'
            f'padding:8px 18px;border-radius:6px;text-decoration:none;font-size:13px;'
            f'font-weight:600;letter-spacing:.2px">+ Google Calendar</a>'
            f'</div>'
        )

    return (
        f'<div style="background:#ffffff;border-left:4px solid {border_color};'
        f'border-radius:0 8px 8px 0;padding:14px 16px;margin-bottom:10px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,.08)">'
        + _badge(ev.get("type", "other"))
        + f'<div style="font-size:15px;font-weight:600;color:#202124;margin-bottom:4px">'
          f'{ev.get("title","")}</div>'
        + meta_line + details + btn +
        '</div>'
    )


def _section_header(title, color, icon_char):
    return (
        f'<div style="margin:28px 0 12px">'
        f'<span style="display:inline-block;width:28px;height:28px;line-height:28px;'
        f'text-align:center;background:{color};border-radius:50%;'
        f'font-size:14px;margin-right:10px;vertical-align:middle">{icon_char}</span>'
        f'<span style="font-size:15px;font-weight:700;color:#202124;vertical-align:middle">{title}</span>'
        f'</div>'
    )


def _content_section(new_content):
    if not new_content:
        return ""

    by_course = {}
    for item in new_content:
        by_course.setdefault(item["course"], []).append(item)

    inner = ""
    for course, items in by_course.items():
        inner += (
            f'<div style="font-size:13px;font-weight:700;color:#34a853;'
            f'margin:10px 0 4px">{course}</div>'
        )
        for item in items:
            ctype = (f' <span style="color:#80868b;font-size:11px">'
                     f'({item["content_type"]})</span>') if item.get("content_type") else ""
            week  = (f' <span style="color:#80868b;font-size:11px;float:right">'
                     f'{item["week"]}</span>') if item.get("week") else ""
            inner += (
                f'<div style="font-size:13px;color:#3c4043;padding:5px 0 5px 12px;'
                f'border-left:2px solid #e0e0e0;margin-bottom:4px">'
                f'{item["title"]}{ctype}{week}'
                f'</div>'
            )

    return (
        _section_header("New Content", "#e6f4ea", "&#9656;") +
        f'<div style="background:#f8fdf9;border:1px solid #ceead6;border-radius:8px;padding:14px 16px">'
        + inner +
        '</div>'
    )


def _build_body_html(events, timezone, new_content=None):
    scheduled     = [ev for ev in events if _is_scheduled(ev)]
    informational = [ev for ev in events if not _is_scheduled(ev)]
    today         = datetime.date.today().strftime("%B %d, %Y")

    # Counts summary chips
    chips = ""
    if scheduled:
        chips += (f'<span style="display:inline-block;background:#e94560;'
                  f'color:#fff;font-size:11px;font-weight:600;padding:3px 10px;'
                  f'border-radius:12px;margin-right:6px">'
                  f'{len(scheduled)} scheduled</span>')
    if informational:
        chips += (f'<span style="display:inline-block;background:rgba(255,255,255,.12);'
                  f'color:rgba(255,255,255,.85);font-size:11px;font-weight:600;padding:3px 10px;'
                  f'border-radius:12px;margin-right:6px;border:1px solid rgba(255,255,255,.2)">'
                  f'{len(informational)} informational</span>')
    if new_content:
        chips += (f'<span style="display:inline-block;background:#00c853;'
                  f'color:#fff;font-size:11px;font-weight:600;padding:3px 10px;'
                  f'border-radius:12px">'
                  f'{len(new_content)} new files</span>')

    header = (
        '<div style="background:#16213e;background-color:#16213e;'
        'padding:28px 24px 24px;border-radius:12px 12px 0 0">'
        '<div style="font-size:24px;font-weight:700;margin-bottom:4px">'
        '<font color="#ffffff">GUC Updates</font></div>'
        f'<div style="font-size:12px;margin-bottom:16px"><font color="#8899bb">{today}</font></div>'
        + chips +
        '</div>'
    )

    sched_section = ""
    if scheduled:
        cards = "".join(_event_card(ev, timezone, show_btn=True, border_color="#1a73e8") for ev in scheduled)
        sched_section = _section_header("Scheduled Events", "#e8f0fe", "&#128197;") + cards

    info_section = ""
    if informational:
        cards = "".join(_event_card(ev, timezone, show_btn=False, border_color="#f9ab00") for ev in informational)
        info_section = _section_header("Informational", "#fef7e0", "&#9432;") + cards

    content_section = _content_section(new_content or [])

    footer = (
        '<div style="margin-top:28px;padding-top:16px;border-top:1px solid #e0e0e0;'
        'font-size:11px;color:#9aa0a6;text-align:center">'
        'GUC Email Parser &nbsp;&#183;&nbsp; events.ics attached for Apple Calendar'
        '</div>'
    )

    # CSS animation block — works in Apple Mail, iOS Mail; gracefully ignored by Gmail
    anim_css = (
        '<style>'
        '@keyframes fadeUp{'
        'from{opacity:0;transform:translateY(12px)}'
        'to{opacity:1;transform:translateY(0)}}'
        '.ev-card{animation:fadeUp .35s ease both}'
        '.ev-card:nth-child(2){animation-delay:.05s}'
        '.ev-card:nth-child(3){animation-delay:.10s}'
        '.ev-card:nth-child(4){animation-delay:.15s}'
        '.ev-card:nth-child(5){animation-delay:.20s}'
        '</style>'
    )

    body = (
        f'<html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        + anim_css +
        '</head>'
        '<body style="margin:0;padding:0;background:#f0f4f9;font-family:-apple-system,'
        'BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif">'
        '<div style="max-width:620px;margin:24px auto;background:#ffffff;'
        'border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.10)">'
        + header +
        '<div style="padding:8px 20px 24px">'
        + sched_section
        + info_section
        + content_section
        + footer +
        '</div>'
        '</div>'
        '</body></html>'
    )
    return body



def send_nothing_new(cfg):
    """Send a short 'nothing new' email when no events or content were found."""
    today = datetime.date.today().strftime("%B %d, %Y")
    body = (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="margin:0;padding:0;background:#f0f4f9;font-family:-apple-system,'
        'BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif">'
        '<div style="max-width:620px;margin:24px auto;background:#ffffff;'
        'border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.10)">'
        '<div style="background:#16213e;background-color:#16213e;padding:28px 24px 24px;border-radius:12px 12px 0 0">'
        '<div style="font-size:24px;font-weight:700;margin-bottom:4px"><font color="#ffffff">GUC Updates</font></div>'
        f'<div style="font-size:12px"><font color="#8899bb">{today}</font></div>'
        '</div>'
        '<div style="padding:32px 24px;text-align:center">'
        '<div style="font-size:40px;margin-bottom:12px">&#10003;</div>'
        '<div style="font-size:16px;font-weight:600;color:#202124;margin-bottom:6px">All caught up</div>'
        '<div style="font-size:13px;color:#5f6368">No new events or content were found today.</div>'
        '</div>'
        '</div>'
        '</body></html>'
    )

    msg = MIMEMultipart("alternative")
    msg["From"]    = cfg["gmail_sender"]
    msg["To"]      = cfg["gmail_recipient"]
    msg["Subject"] = "[GUC] Nothing new"
    msg.attach(MIMEText(body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(cfg["gmail_sender"], cfg["gmail_app_password"])
        smtp.sendmail(cfg["gmail_sender"], cfg["gmail_recipient"], msg.as_string())


def send_events(events, cfg, new_content=None):
    """Send a summary email with .ics attachment for the given events."""
    new_content = new_content or []
    event_count   = len(events)
    content_count = len(new_content)
    parts = []
    if event_count:
        parts.append(f"{event_count} event{'s' if event_count != 1 else ''}")
    if content_count:
        parts.append(f"{content_count} new file{'s' if content_count != 1 else ''}")
    subject = f"[GUC] {', '.join(parts)}"

    ics_str = _build_ics(events, cfg.get("timezone", "Africa/Cairo")).decode("utf-8")

    # Outer container
    msg = MIMEMultipart("mixed")
    msg["From"] = cfg["gmail_sender"]
    msg["To"]   = cfg["gmail_recipient"]
    msg["Subject"] = subject

    alt      = MIMEMultipart("alternative")
    timezone = cfg.get("timezone", "Africa/Cairo")
    alt.attach(MIMEText(_build_body_html(events, timezone, new_content=new_content), "html", "utf-8"))

    cal_inline = MIMEText(ics_str, "calendar", "utf-8")
    cal_inline.set_param("method", "PUBLISH")   # must be on Content-Type itself
    alt.attach(cal_inline)
    msg.attach(alt)

    # Attach .ics for Apple Calendar / other apps
    cal_attach = MIMEBase("text", "calendar")
    cal_attach.set_payload(ics_str.encode("utf-8"))
    cal_attach.set_param("charset", "utf-8")
    cal_attach.set_param("method", "PUBLISH")
    cal_attach.set_param("name", "events.ics")
    cal_attach.add_header("Content-Disposition", "attachment", filename="events.ics")
    msg.attach(cal_attach)

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(cfg["gmail_sender"], cfg["gmail_app_password"])
        smtp.sendmail(cfg["gmail_sender"], cfg["gmail_recipient"], msg.as_string())
