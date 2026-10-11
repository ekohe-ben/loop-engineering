#!/usr/bin/env python3
"""Sends one plain-text Gmail message. Kept out of bin/mail_providers on purpose:
Inbox Triage's providers can never deliver mail (their tests enforce it), so the
only path that can is this module, reached by the chat's approve-gated mail.send
write tool. Only the connected Gmail mailbox is used (gmail.modify covers
messages.send), and every recipient must be a plain address."""
import base64
import re
from email.message import EmailMessage

import mail_http

GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1"
MAX_RECIPIENTS = 10
_ADDRESS = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class SendError(ValueError):
    """A hand-written, secret-free input problem."""


def _addresses(values, label):
    out = []
    for value in values or []:
        value = str(value).strip()
        if not _ADDRESS.match(value):
            raise SendError(f"{label} must be plain email addresses")
        out.append(value)
    return out


def build_raw(sender, to, cc, subject, body):
    to, cc = _addresses(to, "to"), _addresses(cc, "cc")
    if not to:
        raise SendError("at least one recipient is required")
    if len(to) + len(cc) > MAX_RECIPIENTS:
        raise SendError(f"at most {MAX_RECIPIENTS} recipients")
    subject = str(subject)
    if "\r" in subject or "\n" in subject:
        raise SendError("subject must be a single line")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message.set_content(str(body))
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def send_gmail(access_token, sender, to, cc, subject, body, base_url=None):
    raw = build_raw(sender, to, cc, subject, body)
    made = mail_http.request_json("POST", f"{(base_url or GMAIL_BASE_URL).rstrip('/')}/users/me/messages/send",
                                  token=access_token, json_body={"raw": raw}, max_attempts=1)
    return {"id": made.get("id", ""), "thread_id": made.get("threadId", "")}
