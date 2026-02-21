#!/usr/bin/env python3
"""
Simple mail client: send email, check mailbox, open mail, mark as read.
Uses Google IMAP/SMTP with app password. Config from .env or CLI params.
"""

import argparse
import email
import imaplib
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def get_config_from_env():
    """Load config from environment (after loading .env if dotenv is available)."""
    if load_dotenv:
        load_dotenv()
    import os
    return {
        "user": os.environ.get("GMAIL_USER", "").strip(),
        "password": os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip(),
        "imap_host": os.environ.get("IMAP_HOST", "imap.gmail.com"),
        "imap_port": int(os.environ.get("IMAP_PORT", "993")),
        "smtp_host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
    }


def send_email(
    to_addrs,
    subject,
    body,
    *,
    user=None,
    password=None,
    smtp_host=None,
    smtp_port=None,
    from_addr=None,
    body_html=None,
):
    """
    Send an email via SMTP.

    Args:
        to_addrs: Recipient(s) - string or list of strings.
        subject: Subject line.
        body: Plain text body.
        user, password, smtp_host, smtp_port: Override env config if provided.
        from_addr: Sender (defaults to user).
        body_html: Optional HTML body (multipart if provided).
    """
    cfg = get_config_from_env()
    user = user or cfg["user"]
    password = password or cfg["password"]
    smtp_host = smtp_host or cfg["smtp_host"]
    smtp_port = smtp_port or cfg["smtp_port"]
    from_addr = from_addr or user

    if not user or not password:
        raise ValueError("Gmail user and app password are required (set GMAIL_USER and GMAIL_APP_PASSWORD)")

    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]

    if body_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(body_html, "html"))
    else:
        msg = MIMEText(body, "plain")

    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())


def _imap_connection(user=None, password=None, imap_host=None, imap_port=None):
    cfg = get_config_from_env()
    user = user or cfg["user"]
    password = password or cfg["password"]
    imap_host = imap_host or cfg["imap_host"]
    imap_port = imap_port or cfg["imap_port"]
    if not user or not password:
        raise ValueError("Gmail user and app password are required")
    imap = imaplib.IMAP4_SSL(imap_host, imap_port)
    imap.login(user, password)
    return imap


def check_mailbox(
    folder="INBOX",
    *,
    user=None,
    password=None,
    imap_host=None,
    imap_port=None,
    max_count=50,
):
    """
    List emails in the given folder (default INBOX).

    Returns list of dicts: uid, subject, from_addr, date, seen (bool).
    """
    imap = _imap_connection(user=user, password=password, imap_host=imap_host, imap_port=imap_port)
    try:
        imap.select(folder, readonly=True)
        status, data = imap.uid("search", None, "ALL")
        if status != "OK":
            return []
        uid_list = data[0].split()
        if not uid_list:
            return []
        # Fetch from newest; limit to max_count (UIDs are roughly ascending, newest last)
        uid_list = uid_list[-max_count:][::-1]
        result = []
        for uid_bytes in uid_list:
            uid = uid_bytes.decode()
            status, msg_data = imap.uid("fetch", uid_bytes, "(RFC822 FLAGS)")
            if status != "OK" or not msg_data:
                continue
            # Gmail returns FLAGS in a separate response part; collect all to detect \\Seen
            flags = b""
            raw = b""
            for part in msg_data:
                if isinstance(part, tuple):
                    if isinstance(part[0], bytes):
                        flags += part[0]
                    raw = part[1] if len(part) > 1 else b""
                elif isinstance(part, bytes):
                    flags += part
            if raw:
                msg = email.message_from_bytes(raw)
                subject = email.header.decode_header(msg.get("Subject", ""))
                subj_str = ""
                for s, enc in subject:
                    if isinstance(s, bytes):
                        subj_str += s.decode(enc or "utf-8", errors="replace")
                    else:
                        subj_str += s or ""
                from_h = email.header.decode_header(msg.get("From", ""))
                from_str = ""
                for s, enc in from_h:
                    if isinstance(s, bytes):
                        from_str += s.decode(enc or "utf-8", errors="replace")
                    else:
                        from_str += s or ""
                result.append({
                    "uid": uid,
                    "subject": subj_str,
                    "from_addr": from_str,
                    "date": msg.get("Date", ""),
                    "seen": b"\\Seen" in flags,
                })
        return result
    finally:
        imap.logout()


def open_mail(
    uid,
    folder="INBOX",
    *,
    user=None,
    password=None,
    imap_host=None,
    imap_port=None,
):
    """
    Fetch one email by UID. Returns dict with subject, from_addr, date, body_plain, body_html.
    """
    imap = _imap_connection(user=user, password=password, imap_host=imap_host, imap_port=imap_port)
    try:
        imap.select(folder, readonly=True)
        status, msg_data = imap.uid("fetch", str(uid).encode(), "(RFC822)")
        if status != "OK" or not msg_data:
            return None
        for part in msg_data:
            if isinstance(part, tuple) and len(part) > 1:
                raw = part[1]
                break
        else:
            raw = msg_data[0] if msg_data else None
        if not raw:
            return None
        msg = email.message_from_bytes(raw)
        subject = email.header.decode_header(msg.get("Subject", ""))
        subj_str = "".join(
            s.decode(enc or "utf-8", errors="replace") if isinstance(s, bytes) else (s or "")
            for s, enc in subject
        )
        from_h = email.header.decode_header(msg.get("From", ""))
        from_str = "".join(
            s.decode(enc or "utf-8", errors="replace") if isinstance(s, bytes) else (s or "")
            for s, enc in from_h
        )
        body_plain = ""
        body_html = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    body_plain = part.get_payload(decode=True).decode(errors="replace")
                elif ctype == "text/html":
                    body_html = part.get_payload(decode=True).decode(errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body_plain = payload.decode(errors="replace")
        return {
            "uid": uid,
            "subject": subj_str,
            "from_addr": from_str,
            "date": msg.get("Date", ""),
            "body_plain": body_plain,
            "body_html": body_html,
        }
    finally:
        imap.logout()


def mark_as_read(
    uid,
    folder="INBOX",
    *,
    user=None,
    password=None,
    imap_host=None,
    imap_port=None,
):
    """Mark a single email (by UID) as read in the given folder."""
    imap = _imap_connection(user=user, password=password, imap_host=imap_host, imap_port=imap_port)
    try:
        imap.select(folder, readonly=False)
        # Use UID STORE so we update by UID (same as list/open); flags as string for imaplib
        imap.uid("store", str(uid), "+FLAGS", r"(\Seen)")
    finally:
        imap.logout()


def main():
    parser = argparse.ArgumentParser(description="Send email, list mailbox, open mail, mark as read")
    parser.add_argument("--user", help="Gmail address (or set GMAIL_USER)")
    parser.add_argument("--password", help="App password (or set GMAIL_APP_PASSWORD)")
    parser.add_argument("--imap-host", help="IMAP host (default from env or imap.gmail.com)")
    parser.add_argument("--imap-port", type=int, help="IMAP port (default from env or 993)")
    parser.add_argument("--smtp-host", help="SMTP host (default from env or smtp.gmail.com)")
    parser.add_argument("--smtp-port", type=int, help="SMTP port (default from env or 587)")

    sub = parser.add_subparsers(dest="command", required=True)

    # send
    p_send = sub.add_parser("send", help="Send an email")
    p_send.add_argument("--to", required=True, help="Recipient email")
    p_send.add_argument("--subject", required=True, help="Subject")
    p_send.add_argument("--body", required=True, help="Body text")

    # list
    p_list = sub.add_parser("list", help="List emails in mailbox")
    p_list.add_argument("--folder", default="INBOX", help="Mailbox folder")
    p_list.add_argument("--max", type=int, default=20, help="Max emails to list")

    # open
    p_open = sub.add_parser("open", help="Open (fetch) one email by UID")
    p_open.add_argument("uid", help="Email UID from list")
    p_open.add_argument("--folder", default="INBOX", help="Mailbox folder")

    # mark-read
    p_mark = sub.add_parser("mark-read", help="Mark an email as read by UID")
    p_mark.add_argument("uid", help="Email UID from list")
    p_mark.add_argument("--folder", default="INBOX", help="Mailbox folder")

    args = parser.parse_args()
    opts = {
        "user": args.user,
        "password": args.password,
        "imap_host": args.imap_host,
        "imap_port": args.imap_port,
        "smtp_host": args.smtp_host,
        "smtp_port": args.smtp_port,
    }

    try:
        if args.command == "send":
            send_email(
                args.to,
                args.subject,
                args.body,
                user=opts["user"],
                password=opts["password"],
                smtp_host=opts["smtp_host"],
                smtp_port=opts["smtp_port"],
            )
            print("Email sent to", args.to)

        elif args.command == "list":
            emails = check_mailbox(
                folder=args.folder,
                user=opts["user"],
                password=opts["password"],
                imap_host=args.imap_host,
                imap_port=args.imap_port,
                max_count=args.max,
            )
            for e in emails:
                unread = "" if e["seen"] else " (unread)"
                print(f"UID {e['uid']}{unread} | {e['date']} | {e['from_addr'][:40]} | {e['subject'][:50]}")

        elif args.command == "open":
            mail = open_mail(
                args.uid,
                folder=args.folder,
                user=opts["user"],
                password=opts["password"],
                imap_host=args.imap_host,
                imap_port=args.imap_port,
            )
            if not mail:
                print("Email not found", file=sys.stderr)
                sys.exit(1)
            print("From:", mail["from_addr"])
            print("Date:", mail["date"])
            print("Subject:", mail["subject"])
            print("-" * 40)
            print(mail["body_plain"] or mail["body_html"] or "(no body)")

        elif args.command == "mark-read":
            mark_as_read(
                args.uid,
                folder=args.folder,
                user=opts["user"],
                password=opts["password"],
                imap_host=args.imap_host,
                imap_port=args.imap_port,
            )
            print("Marked UID", args.uid, "as read")

    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
