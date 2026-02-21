# Simple Mail

A small Python client for Gmail and Google Calendar: send email, list mailbox, open/mark mail, and **check calendar** — all with the **same app password**. Config via `.env` or CLI arguments.

## Setup

1. **Python 3.7+** (uses only standard library for IMAP/SMTP; optional `python-dotenv` for `.env`).

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Google (App Password):**
   - Turn on [2-Step Verification](https://myaccount.google.com/signinoptions/two-step-verification) for your Google account.
   - Create an [App Password](https://myaccount.google.com/apppasswords) (e.g. for “Mail”) and copy the 16-character password. The same app password works for **mail (IMAP/SMTP)** and **calendar (CalDAV)**.

4. **Create your `.env` file:**
   ```bash
   copy .env.example .env
   ```
   Edit `.env` and set:
   - `GMAIL_USER` — your Gmail address
   - `GMAIL_APP_PASSWORD` — the app password (spaces optional)

   Optional overrides (defaults are for Gmail):
   - `IMAP_HOST`, `IMAP_PORT` (default: `imap.gmail.com`, `993`)
   - `SMTP_HOST`, `SMTP_PORT` (default: `smtp.gmail.com`, `587`)

## CLI Usage

All commands use `.env` by default. You can override with `--user` and `--password` (and `--imap-host`, `--imap-port`, `--smtp-host`, `--smtp-port`).

### Send email
```bash
python mail_client.py send --to "recipient@example.com" --subject "Hello" --body "Your message here"
```

### List emails (check mailbox)
```bash
python mail_client.py list
python mail_client.py list --folder INBOX --max 30
```

### Open one email (by UID from list)
```bash
python mail_client.py open 123
python mail_client.py open 123 --folder INBOX
```

### Mark email as read
```bash
python mail_client.py mark-read 123
python mail_client.py mark-read 123 --folder INBOX
```

### Override credentials (no .env)
```bash
python mail_client.py --user you@gmail.com --password "your-app-password" list
python mail_client.py --user you@gmail.com --password "your-app-password" send --to "x@y.com" --subject "Hi" --body "Text"
```

## Calendar (same app password)

The same `GMAIL_USER` and `GMAIL_APP_PASSWORD` from `.env` are used to read Google Calendar via CalDAV.

### List calendars
```bash
python calendar_client.py calendars
python calendar_client.py calendars -v   # full URL and id
```

**Shared calendars ("Other calendars")** — Google does not expose calendars shared with you (e.g. colleague@work.example.com, other@gmail.com) via CalDAV until you enable them for sync:

1. Open **[Google Calendar sync select](https://www.google.com/calendar/syncselect)** (while signed in as your Google account).
2. Check the calendars you want to sync (your primary, shared work calendar, other shared calendars, etc.).
3. Save. After that, `python calendar_client.py calendars` will list them and you can use `--calendar <id>` for events.

### List events
```bash
python calendar_client.py events
python calendar_client.py events --days-past 7 --days-ahead 30 --max 50
python calendar_client.py events --calendar "your@gmail.com"
```

If you get **401 Unauthorized**, Google may require OAuth for CalDAV for your account; the app password will still work for mail (IMAP/SMTP).

## Use as a Python module

```python
from mail_client import send_email, check_mailbox, open_mail, mark_as_read

# Uses .env by default
send_email("recipient@example.com", "Subject", "Body text")

emails = check_mailbox(folder="INBOX", max_count=10)
for e in emails:
    print(e["uid"], e["subject"], e["from_addr"], "read" if e["seen"] else "unread")

mail = open_mail(emails[0]["uid"])
print(mail["subject"], mail["body_plain"])

mark_as_read(emails[0]["uid"])
```

With explicit credentials (no .env):

```python
send_email(
    "to@example.com", "Subject", "Body",
    user="you@gmail.com",
    password="your-app-password",
)
emails = check_mailbox(user="you@gmail.com", password="your-app-password", max_count=5)
mail = open_mail(emails[0]["uid"], user="you@gmail.com", password="your-app-password")
mark_as_read(emails[0]["uid"], user="you@gmail.com", password="your-app-password")
```

**Calendar (same credentials):**
```python
from calendar_client import list_calendars, list_events
from datetime import datetime, timedelta

for cal in list_calendars():
    print(cal["id"], cal["name"])
events = list_events(
    start=datetime.now() - timedelta(days=7),
    end=datetime.now() + timedelta(days=14),
)
for e in events:
    print(e["start"], e["summary"], e["location"])
```

## API summary

| Function         | Purpose |
|------------------|--------|
| `send_email(to, subject, body, ...)` | Send an email (optional `body_html`, `user`, `password`, `smtp_host`, `smtp_port`, `from_addr`). |
| `check_mailbox(folder="INBOX", ...)` | Return list of `{uid, subject, from_addr, date, seen}` (optional `max_count`, `user`, `password`, `imap_host`, `imap_port`). |
| `open_mail(uid, folder="INBOX", ...)` | Fetch one message; returns `{uid, subject, from_addr, date, body_plain, body_html}`. |
| `mark_as_read(uid, folder="INBOX", ...)` | Set the `\Seen` flag on the message. |

**Calendar** (`calendar_client.py`):

| Function | Purpose |
|----------|---------|
| `list_calendars(user=..., password=...)` | List calendars (uses `.env` if no args). |
| `list_events(start, end, calendar_id=..., ...)` | List events in range (optional `calendar_id`, `max_results`). |

## Security

- **Do not commit `.env`** — it contains your app password. Only commit `.env.example`.
- Use an **App Password**, not your normal Gmail password.
- Keep `.env` in `.gitignore` if you use git.
