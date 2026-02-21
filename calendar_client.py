#!/usr/bin/env python3
"""
Check Google Calendar using the same app password as mail (.env: GMAIL_USER, GMAIL_APP_PASSWORD).
Uses CalDAV; works with personal Google accounts that have 2-Step Verification and an app password.
If you get 401, Google may require OAuth for your account—see README.
"""

import argparse
import sys
from datetime import date, datetime, timedelta

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import caldav
except ImportError:
    caldav = None


def get_config():
    """Load Gmail user and app password from .env (same as mail_client)."""
    if load_dotenv:
        load_dotenv()
    import os
    return {
        "user": os.environ.get("GMAIL_USER", "").strip(),
        "password": os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip(),
    }


def _caldav_client(user=None, password=None):
    """Build CalDAV client for Google. Uses legacy endpoint that accepts app password."""
    cfg = get_config()
    user = user or cfg["user"]
    password = password or cfg["password"]
    if not user or not password:
        raise ValueError("GMAIL_USER and GMAIL_APP_PASSWORD are required (same as mail)")
    if not caldav:
        raise ImportError("Install caldav: pip install caldav")

    # Google legacy CalDAV endpoint; same app password as IMAP/SMTP.
    # For primary calendar, calendar ID is the user's email.
    url = "https://calendar.google.com/calendar/dav/"
    client = caldav.DAVClient(url=url, username=user, password=password)
    return client


def list_calendars(*, user=None, password=None):
    """
    List calendars the account can see via CalDAV.
    Returns list of dicts: name, url, id.

    Note: Google only exposes shared calendars ("Other calendars") after you
    enable them at https://www.google.com/calendar/syncselect
    """
    client = _caldav_client(user=user, password=password)
    principal = client.principal()
    calendars = principal.calendars()
    result = []
    for cal in calendars:
        name = getattr(cal, "name", None) or ""
        if hasattr(cal, "get_display_name") and callable(cal.get_display_name):
            try:
                name = cal.get_display_name() or name
            except Exception:
                pass
        url = cal.url if hasattr(cal, "url") else ""
        path_parts = url.rstrip("/").split("/")
        # Google: .../calendar/dav/CALENDAR_ID/events -> id is second-to-last
        if path_parts and path_parts[-1].lower() == "events":
            cal_id = path_parts[-2] if len(path_parts) >= 2 else path_parts[-1]
        else:
            cal_id = path_parts[-1] if path_parts else ""
        result.append({"name": name, "url": url, "id": cal_id})
    return result


def list_events(
    start=None,
    end=None,
    calendar_id=None,
    *,
    user=None,
    password=None,
    max_results=100,
):
    """
    List events in a date range. Uses primary calendar if calendar_id is None.

    start/end: date or datetime; default last 7 days to next 30 days.
    Returns list of dicts: summary, start, end, uid, location, description.
    """
    client = _caldav_client(user=user, password=password)
    cfg = get_config()
    email = (user or cfg["user"]).strip()

    if start is None:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
    if end is None:
        end = datetime.now() + timedelta(days=30)

    # caldav search() accepts date or datetime
    if isinstance(start, datetime):
        start = start.date() if hasattr(start, "date") else start
    if isinstance(end, datetime):
        end = end.date() if hasattr(end, "date") else end

    principal = client.principal()
    calendars = principal.calendars()

    # Pick calendar: by id (e.g. user@gmail.com or xxx@group.calendar.google.com) or first
    calendar = None
    if calendar_id:
        for cal in calendars:
            url = getattr(cal, "url", "") or ""
            if calendar_id in url or url.rstrip("/").endswith(calendar_id):
                calendar = cal
                break
    if not calendar and calendars:
        calendar = calendars[0]
    if not calendar:
        return []

    events = calendar.search(start=start, end=end, event=True, expand=True)
    result = []
    for e in events[:max_results]:
        comp = getattr(e, "component", None)
        if not comp:
            continue
        s = comp.get("summary", "") or ""
        if hasattr(s, "to_ical"):
            summary = s.to_ical().decode("utf-8", errors="replace")
        else:
            summary = str(s)
        uid = comp.get("uid", "")
        if hasattr(uid, "to_ical"):
            uid = uid.to_ical().decode("utf-8", errors="replace")
        dt_start = comp.get("dtstart")
        dt_end = comp.get("dtend")
        loc = comp.get("location", "")
        if hasattr(loc, "to_ical") and loc:
            loc = loc.to_ical().decode("utf-8", errors="replace")
        else:
            loc = str(loc) if loc else ""
        desc = comp.get("description", "")
        if hasattr(desc, "to_ical") and desc:
            desc = desc.to_ical().decode("utf-8", errors="replace")
        else:
            desc = str(desc) if desc else ""

        def _dt(d):
            if d is None:
                return None
            if hasattr(d, "dt"):
                return d.dt
            return d

        result.append({
            "summary": summary or "(no title)",
            "start": _dt(dt_start),
            "end": _dt(dt_end),
            "uid": uid,
            "location": loc,
            "description": desc,
        })
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Check Google Calendar (same app password as mail)"
    )
    parser.add_argument("--user", help="Gmail address (or set GMAIL_USER)")
    parser.add_argument("--password", help="App password (or set GMAIL_APP_PASSWORD)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cals = sub.add_parser("calendars", help="List calendars (includes shared/subscribed)")
    p_cals.add_argument("--verbose", "-v", action="store_true", help="Show full URL and id")

    p_events = sub.add_parser("events", help="List events in date range")
    p_events.add_argument("--calendar", dest="calendar_id", help="Calendar ID (default: primary)")
    p_events.add_argument("--days-past", type=int, default=7, help="Days in the past to include")
    p_events.add_argument("--days-ahead", type=int, default=30, help="Days ahead to include")
    p_events.add_argument("--max", type=int, default=50, help="Max events to return")

    args = parser.parse_args()
    user, password = args.user, args.password

    try:
        if args.command == "calendars":
            cals = list_calendars(user=user, password=password)
            for c in cals:
                if getattr(args, "verbose", False):
                    print(f"  name: {c['name'] or '(no name)'}")
                    print(f"  id:   {c['id']}")
                    print(f"  url:  {c['url']}")
                    print()
                else:
                    print(f"  {c['id']}  {c['name'] or '(no name)'}")
            if cals and not getattr(args, "verbose", False):
                print()
                print("  Missing shared calendars (Other calendars)? Enable them for CalDAV at:")
                print("  https://www.google.com/calendar/syncselect")

        elif args.command == "events":
            start = datetime.now() - timedelta(days=args.days_past)
            end = datetime.now() + timedelta(days=args.days_ahead)
            events = list_events(
                start=start,
                end=end,
                calendar_id=args.calendar_id,
                user=user,
                password=password,
                max_results=args.max,
            )
            for e in events:
                start_str = e["start"] if e["start"] is None else str(e["start"])
                end_str = e["end"] if e["end"] is None else str(e["end"])
                loc = f" @ {e['location']}" if e["location"] else ""
                print(f"  {start_str} – {end_str}  {e['summary']}{loc}")

    except Exception as err:
        if "401" in str(err) or "Unauthorized" in str(err):
            print(
                "Calendar returned 401. Google may require OAuth for CalDAV for your account. "
                "Use the same app password only for mail (IMAP/SMTP).",
                file=sys.stderr,
            )
        print(err, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
