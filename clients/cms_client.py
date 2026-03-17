"""
Scrapes the GUC CMS for course announcements, quiz/event information,
new content items, and a course-code → full-name map.
The CMS uses Windows/NTLM authentication (the browser popup).
"""
import hashlib
import re
import urllib.parse

import requests
import urllib3
from bs4 import BeautifulSoup
from requests_ntlm import HttpNtlmAuth

import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = config.print_if_dev


def _cms_session(cfg):
    """Return (session, base_url) authenticated via NTLM."""
    session       = requests.Session()
    session.verify = False
    base_url      = cfg["cms_url"].rstrip("/")
    session.auth  = HttpNtlmAuth(cfg["cms_user"], cfg["cms_password"])

    resp = session.get(f"{base_url}/apps/student/HomePageStn.aspx", timeout=30)
    if resp.status_code == 401:
        raise RuntimeError(
            "CMS authentication failed (401).\n"
            "Check CMS_USER (try 'GUC\\\\yourname' or just 'yourname') "
            "and CMS_PASSWORD in your .env."
        )
    resp.raise_for_status()
    return session, base_url


def _course_links(soup, base_url):
    """Return deduplicated list of {url} from the sidebar course links."""
    seen, courses = set(), []
    for a in soup.select("a[href*='CourseViewStn.aspx']"):
        href = a.get("href", "")
        url  = urllib.parse.urljoin(base_url, href)
        if href and url not in seen:
            seen.add(url)
            courses.append(url)
    return courses


def _parse_course_header(raw):
    """
    Parse the LabelCourseName span text.
    Input:  "(|NETW1009|) Cloud Computing (ISM) (1705)"
    Returns: (code, full_name)  e.g. ("NETW1009", "Cloud Computing (ISM)")
    """
    code_m = re.search(r'\(\|([^|]+)\|\)', raw)
    code   = code_m.group(1).strip() if code_m else None
    name   = re.sub(r'^\(\|[^|]+\|\)\s*', '', raw)   # strip code prefix
    name   = re.sub(r'\s*\(\d+\)\s*$', '', name).strip()  # strip trailing (1705)
    return code, name


def _course_full_name(soup):
    tag = soup.find("span", id=lambda x: x and "LabelCourseName" in (x or ""))
    return tag.get_text(strip=True) if tag else ""


def _extract_documents(soup, course_name):
    """Text blobs worth sending to Ollama (announcements)."""
    docs = []

    # Top-level course announcement
    desc_div = soup.find("div", id=lambda x: x and x.endswith("_desc"))
    if desc_div:
        text = desc_div.get_text(separator="\n").strip()
        if text:
            docs.append({
                "subject": f"[CMS] {course_name}",
                "sender":  course_name,
                "date":    "",
                "body":    text,
            })

    # Per-week announcement paragraphs
    for card in soup.select(".weeksdata"):
        week_tag  = card.select_one("h2.text-big")
        week_date = week_tag.get_text(strip=True).replace("Week:", "").strip() if week_tag else ""

        inner = card.select_one(".p-3")
        if not inner:
            continue

        for div in inner.find_all("div", recursive=False):
            strong = div.find("strong")
            if not strong or strong.get_text(strip=True).lower() != "announcement":
                continue
            style = div.get("style", "")
            if "display:none" in style.replace(" ", ""):
                continue
            p    = div.find("p", class_="p2")
            text = p.get_text(strip=True) if p else ""
            if text:
                docs.append({
                    "subject": f"[CMS] {course_name} — {week_date}",
                    "sender":  course_name,
                    "date":    week_date,
                    "body":    text,
                })

    return docs


def _extract_content_items(soup, course_name):
    """
    New lecture/VoD/file items posted per week.
    Returns list of {course, week, title, content_type}.
    """
    items = []
    for card in soup.select(".weeksdata"):
        week_tag  = card.select_one("h2.text-big")
        week_date = week_tag.get_text(strip=True).replace("Week:", "").strip() if week_tag else ""

        for cb in card.select(".card-body"):
            title_div = cb.find("div", id=re.compile(r'^content\d+$'))
            if not title_div:
                continue
            full_text = title_div.get_text(strip=True)
            # Extract type from trailing parentheses: "1 - Lecture 6 (Lecture slides)"
            type_m       = re.search(r'\(([^)]+)\)\s*$', full_text)
            content_type = type_m.group(1) if type_m else ""
            title        = re.sub(r'\s*\([^)]*\)\s*$', '', full_text).strip()

            items.append({
                "course":       course_name,
                "week":         week_date,
                "title":        title,
                "content_type": content_type,
            })

    return items


def content_hash(doc):
    """16-char hash for deduplication."""
    raw = f"{doc['subject']}|{doc['sender']}|{doc['body']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def content_item_hash(item):
    raw = f"{item['course']}|{item['week']}|{item['title']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fetch_cms_data(cfg):
    """
    Login, scrape all course pages.
    Returns:
      docs          — list of announcement dicts for Ollama
      course_map    — {code: full_name}  e.g. {"NETW1009": "Cloud Computing (ISM)"}
      content_items — list of new content item dicts
    """
    log("Connecting to CMS...")
    session, base_url = _cms_session(cfg)
    log("CMS login successful.")

    home_url = f"{base_url}/apps/student/HomePageStn.aspx"
    resp     = session.get(home_url, verify=False, timeout=30)
    soup     = BeautifulSoup(resp.text, "html.parser")
    urls     = _course_links(soup, base_url)
    log(f"Found {len(urls)} course(s) on CMS.")

    all_docs     = []
    all_items    = []
    course_map   = {}

    for url in urls:
        resp  = session.get(url, verify=False, timeout=30)
        soup  = BeautifulSoup(resp.text, "html.parser")
        raw   = _course_full_name(soup)
        code, full_name = _parse_course_header(raw)
        course_name = full_name or raw or "Unknown Course"

        if code and full_name:
            course_map[code] = full_name

        docs  = _extract_documents(soup, course_name)
        items = _extract_content_items(soup, course_name)

        if docs or items:
            log(f"  {course_name}: {len(docs)} announcement(s), {len(items)} content item(s).")

        all_docs.extend(docs)
        all_items.extend(items)

    return all_docs, course_map, all_items


# Keep old name as alias so test-cms.py still works
def fetch_cms_documents(cfg):
    docs, _, _ = fetch_cms_data(cfg)
    return docs
